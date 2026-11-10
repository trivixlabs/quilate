from datetime import UTC, datetime

import ccxt
import pytest

from quilate.exchanges.client import ExchangeClient, UnsafeKeyError, make_clients

NOW = datetime.now(UTC)
MS = int(NOW.timestamp() * 1000)


class StubEx:
    def __init__(self, restrictions=None, my_trades=(), converts=(), ohlcv=None):
        self.markets = {"BTC/USDT": {}, "ABC/BTC": {}}
        self.restrictions, self.my_trades, self.converts = restrictions, list(my_trades), list(converts)
        self.ohlcv = ohlcv or {}
        self.convert_calls = 0

    async def load_markets(self):
        pass

    async def sapi_get_account_apirestrictions(self):
        return self.restrictions

    async def private_get_v5_user_query_api(self):
        return self.restrictions

    async def fetch_my_trades(self, pair, since=None, limit=None, params=None):
        # como a API: sem paginação do ccxt, uma página só (de até 100)
        rows = sorted((t for t in self.my_trades if t["pair"] == pair and (since is None or t["timestamp"] >= since)),
                      key=lambda t: t["timestamp"])
        return rows if (params or {}).get("paginate") else rows[:limit or 100]

    async def fetch_ohlcv(self, pair, tf, since, limit):
        return self.ohlcv[pair]

    async def sapi_get_convert_tradeflow(self, p):
        self.convert_calls += 1
        return {"list": [c for c in self.converts if p["startTime"] <= c["createTime"] <= p["endTime"]]}


BINANCE_SAFE = {"enableReading": True, "enableFixReadOnly": True, "enableWithdrawals": False,
                "enableSpotAndMarginTrading": False, "enableFutures": False, "enableMargin": False,
                "enableVanillaOptions": False, "enablePortfolioMarginTrading": False,
                "enableInternalTransfer": False, "permitsUniversalTransfer": False, "enableFixApiTrade": False}


@pytest.mark.parametrize("r,unsafe", [
    (BINANCE_SAFE, False),
    ({**BINANCE_SAFE, "enableWithdrawals": True}, True),
    ({**BINANCE_SAFE, "enableSpotAndMarginTrading": True}, True),
    ({**BINANCE_SAFE, "enableFutures": True}, True),
    ({**BINANCE_SAFE, "permitsUniversalTransfer": True}, True),
    ({**BINANCE_SAFE, "enableNovaPermissao": True}, True),  # campo novo da Binance também conta
    ({k: v for k, v in BINANCE_SAFE.items() if k != "enableMargin"}, True),  # campo ausente: falha fechada
    ({"enableWithdrawals": False, "enableSpotAndMarginTrading": False}, True),
    ({}, True),
])
async def test_binance_check_read_only(r, unsafe):
    c = ExchangeClient("binance", StubEx(r))
    if unsafe:
        with pytest.raises(UnsafeKeyError):
            await c.check_read_only()
    else:
        await c.check_read_only()


@pytest.mark.parametrize("r,unsafe", [
    ({"retCode": 0, "result": {"readOnly": 1, "permissions": {"Spot": []}}}, False),
    ({"retCode": 0, "result": {"readOnly": 0, "permissions": {"Spot": ["SpotTrade"]}}}, True),
    ({"retCode": 0, "result": {}}, True),
    ({}, True),
])
async def test_bybit_check_read_only(r, unsafe):
    c = ExchangeClient("bybit", StubEx(r))
    if unsafe:
        with pytest.raises(UnsafeKeyError):
            await c.check_read_only()
    else:
        await c.check_read_only()


@pytest.mark.parametrize("name", ["mexc", "gate"])
async def test_unverified_exchange_refused_until_owner_confirms(name):
    with pytest.raises(UnsafeKeyError) as e:
        await ExchangeClient(name, StubEx()).check_read_only()
    assert "confirmed_read_only" in str(e.value) and "config.local.toml" in str(e.value)
    await ExchangeClient(name, StubEx(), confirmed=True).check_read_only()


async def test_make_clients_marks_confirmed_exchanges(memory_keyring):
    from dataclasses import replace

    from quilate.config import load_settings
    for k in ("mexc_key", "mexc_secret", "gate_key", "gate_secret"):
        memory_keyring.set_password("quilate", k, "x")
    clients = make_clients(replace(load_settings(), confirmed_read_only=frozenset({"mexc"})))
    try:
        assert clients["mexc"].confirmed and not clients["gate"].confirmed
    finally:
        for c in clients.values():
            await c.close()


def _trade(pair, fee_ccy, fee_cost, price=100.0):
    return {"pair": pair, "id": 1, "timestamp": MS, "side": "buy", "amount": 2.0, "price": price,
            "fee": {"currency": fee_ccy, "cost": fee_cost}}


async def test_fetch_trades_fee_in_quote_and_base():
    ex = StubEx(my_trades=[_trade("BTC/USDT", "USDT", 0.5)])
    t = (await ExchangeClient("mexc", ex).fetch_trades("BTC", None))[0]
    assert t.price_usd == 100.0 and t.fee_usd == pytest.approx(0.5) and t.source == "api"
    ex = StubEx(my_trades=[_trade("BTC/USDT", "BTC", 0.01)])
    t = (await ExchangeClient("mexc", ex).fetch_trades("BTC", None))[0]
    assert t.fee_usd == pytest.approx(1.0)


async def test_fetch_trades_non_stable_quote_uses_daily_candle():
    candle = [[MS, 1, 1, 1, 20000.0, 5]]
    ex = StubEx(my_trades=[_trade("ABC/BTC", "BTC", 0.001, price=0.01)], ohlcv={"BTC/USDT": candle})
    t = (await ExchangeClient("mexc", ex).fetch_trades("ABC", None))[0]
    assert t.price_usd == pytest.approx(200.0) and t.fee_usd == pytest.approx(20.0)


async def test_candle_volume_is_quote():
    ex = StubEx(ohlcv={"BTC/USDT": [[MS, 1, 3, 1, 2.0, 10]]})
    c = (await ExchangeClient("binance", ex).fetch_daily_candles("BTC", "USDT", 1))[0]
    assert c.volume_quote == 20.0


async def test_convert_legs_have_equal_usd_value_and_history_fetched_once():
    conv = {"orderId": 7, "orderStatus": "SUCCESS", "createTime": MS, "fromAsset": "USDT", "fromAmount": "100",
            "toAsset": "BTC", "toAmount": "0.005"}
    ex = StubEx(converts=[conv], ohlcv={"BTC/USDT": [[MS, 1, 1, 1, 20000.0, 1]]})
    c = ExchangeClient("binance", ex)
    sell = (await c.fetch_trades("USDT", None))[0]
    calls = ex.convert_calls
    buy = (await c.fetch_trades("BTC", None))[0]
    assert ex.convert_calls == calls
    assert (sell.side, buy.side) == ("sell", "buy")
    assert sell.qty * sell.price_usd == pytest.approx(buy.qty * buy.price_usd) == pytest.approx(100.0)


class FakePro:
    """ccxt.pro com um par só: pedir par sem mercado USDT ativo é BadSymbol."""
    def __init__(self):
        self.asked = []

    async def load_markets(self):
        return {"BTC/USDT": {"active": True}, "OLD/USDT": {"active": False}, "ABC/BTC": {}}

    async def watch_tickers(self, pairs):
        self.asked.append(pairs)
        if any(p != "BTC/USDT" for p in pairs):
            raise ccxt.BadSymbol(f"sem mercado: {pairs}")
        return {"BTC/USDT": {"last": 50000.0, "timestamp": MS}}


async def test_watch_tickers_skips_assets_without_usdt_market(caplog):
    c = ExchangeClient("binance", StubEx())
    c._pro = FakePro()
    for _ in range(2):
        ticks = await c.watch_tickers(["BTC", "OLD", "ABC"])
    assert [(t.symbol, t.last) for t in ticks] == [("BTC", 50000.0)]
    assert c._pro.asked == [["BTC/USDT"]] * 2
    assert sum("ABC" in r.message and "OLD" in r.message for r in caplog.records) == 1  # avisa uma vez só


@pytest.mark.parametrize("name", ["mexc", "binance"])
async def test_fetch_trades_reads_every_page(name):
    old = [{**_trade("BTC/USDT", "USDT", 0.0), "id": i, "timestamp": MS - (i + 1) * 60_000} for i in range(250)]
    t = await ExchangeClient(name, StubEx(my_trades=old)).fetch_trades("BTC", None)
    assert sorted(x.trade_id for x in t) == sorted(str(i) for i in range(250))


async def test_fee_in_third_currency_uses_that_day_close():
    ex = StubEx(my_trades=[_trade("BTC/USDT", "BNB", 0.01)], ohlcv={"BNB/USDT": [[MS, 1, 1, 1, 600.0, 1]]})
    t = (await ExchangeClient("binance", ex).fetch_trades("BTC", None))[0]
    assert t.fee_usd == pytest.approx(6.0)

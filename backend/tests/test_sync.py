from dataclasses import replace
from datetime import UTC, datetime, timedelta

import ccxt.async_support as ccxt
import pytest

from quilate.exchanges.client import Holding, UnsafeKeyError
from quilate.exchanges.cost_basis import Trade
from quilate.exchanges.sync import insert_trades, sync_all

NOW = datetime(2025, 3, 1, tzinfo=UTC)


class FakeClient:
    def __init__(self, name, holdings=(), trades=(), error=None, unsafe=False):
        self.name, self.holdings, self.trades, self.error, self.unsafe = name, list(holdings), list(trades), error, unsafe
        self.asked = []

    async def check_read_only(self):
        if self.unsafe:
            raise UnsafeKeyError(self.name)

    async def fetch_holdings(self):
        if self.error:
            raise self.error
        return self.holdings

    async def fetch_trades(self, symbol, since_utc):
        self.asked.append(symbol)
        return [t for t in self.trades if t.symbol == symbol]

    async def close(self):
        pass


def _notifier(sent):
    async def notify(m):
        sent.append(m)
    return notify


async def test_one_exchange_down_others_saved(db):
    clients = {"binance": FakeClient("binance", [Holding("binance", "BTC", "spot", 0.4)]),
               "bybit": FakeClient("bybit", error=ccxt.PermissionDenied("403"))}
    sent = []
    rep = await sync_all(db, clients, notify=_notifier(sent), now=NOW)
    assert rep.ok == ["binance"] and "bybit" in rep.failed
    assert db.execute("SELECT qty FROM positions WHERE exchange='binance'").fetchone()[0] == 0.4
    assert db.execute("SELECT stale FROM positions WHERE exchange='bybit'").fetchall() == []
    assert len(sent) == 1 and "Bybit" in sent[0]


async def test_previous_positions_marked_stale(db):
    db.execute("INSERT INTO positions VALUES ('bybit','ETH','spot',2,'2025-02-01T00:00:00+00:00',0)")
    clients = {"bybit": FakeClient("bybit", error=ccxt.NetworkError("down"))}
    await sync_all(db, clients, notify=_notifier([]), now=NOW)
    assert db.execute("SELECT stale FROM positions WHERE exchange='bybit'").fetchone()[0] == 1


async def test_success_replaces_positions_normalizes_and_saves_trades(db):
    db.execute("INSERT INTO positions VALUES ('binance','OLD','spot',1,'2025-02-01T00:00:00+00:00',1)")
    tr = Trade("binance", "1", "BTC", "buy", 0.4, 50000, 1, NOW, "api")
    c = FakeClient("binance", [Holding("binance", "BTC", "spot", 0.3), Holding("binance", "LDBTC", "spot", 0.1)], [tr])
    await sync_all(db, {"binance": c}, notify=_notifier([]), now=NOW)
    await sync_all(db, {"binance": c}, notify=_notifier([]), now=NOW)  # idempotente
    rows = db.execute("SELECT symbol, wallet, qty, stale FROM positions ORDER BY wallet").fetchall()
    assert [tuple(r) for r in rows] == [("BTC", "earn", 0.1, 0), ("BTC", "spot", 0.3, 0)]
    assert db.execute("SELECT count(*) FROM trades").fetchone()[0] == 1


async def test_unsafe_key_blocks_sync(db):
    c = FakeClient("binance", unsafe=True)
    with pytest.raises(UnsafeKeyError):
        await c.check_read_only()
    with pytest.raises(UnsafeKeyError):
        await sync_all(db, {"binance": c}, notify=_notifier([]), now=NOW)


async def test_unsafe_key_later_blocks_before_any_write(db):
    clients = {"binance": FakeClient("binance", [Holding("binance", "BTC", "spot", 1)]),
               "bybit": FakeClient("bybit", unsafe=True)}
    with pytest.raises(UnsafeKeyError):
        await sync_all(db, clients, notify=_notifier([]), now=NOW)
    assert db.execute("SELECT count(*) FROM positions").fetchone()[0] == 0


async def test_check_read_only_network_error_is_isolated(db):
    class Flaky(FakeClient):
        async def check_read_only(self):
            raise ccxt.NetworkError("down")

    sent = []
    clients = {"binance": Flaky("binance"), "gate": FakeClient("gate", [Holding("gate", "ETH", "spot", 2)])}
    rep = await sync_all(db, clients, notify=_notifier(sent), now=NOW)
    assert rep.ok == ["gate"] and "binance" in rep.failed and len(sent) == 1


async def test_notify_failure_does_not_abort_others(db):
    async def boom(m):
        raise RuntimeError("telegram")

    clients = {"bybit": FakeClient("bybit", error=ccxt.NetworkError("x")),
               "gate": FakeClient("gate", [Holding("gate", "ETH", "spot", 2)])}
    rep = await sync_all(db, clients, notify=boom, now=NOW)
    assert rep.ok == ["gate"]


async def test_error_alert_has_only_the_exception_type(db):
    # a mensagem do ccxt pode trazer a URL assinada: nem o log nem o alerta a repetem
    err = ccxt.PermissionDenied("bybit GET https://api.bybit.com/v5/x?sign=abc123&timestamp=1")
    sent = []
    rep = await sync_all(db, {"bybit": FakeClient("bybit", error=err)}, notify=_notifier(sent), now=NOW)
    assert rep.failed["bybit"] == "PermissionDenied"
    assert "PermissionDenied" in sent[0] and "sign=" not in sent[0]


API_TRADE = Trade("binance", "987", "BTC", "buy", 0.1, 50000, 1, datetime(2025, 3, 1, 10, 0, 0, 345000, tzinfo=UTC), "api")
CSV_TRADE = Trade("binance", "a1b2c3", "BTC", "buy", 0.1 + 1e-9, 50000, 1, datetime(2025, 3, 1, 10, 0, 0, tzinfo=UTC), "csv")


@pytest.mark.parametrize("first,second", [(API_TRADE, CSV_TRADE), (CSV_TRADE, API_TRADE)])
def test_same_trade_from_api_and_csv_counts_once(db, first, second):
    assert insert_trades(db, [first]) == 1
    assert insert_trades(db, [second]) == 0
    assert [tuple(r) for r in db.execute("SELECT source FROM trades")] == [(first.source,)]


def test_insert_trades_keeps_different_trades(db):
    other_second = replace(CSV_TRADE, ts_utc=CSV_TRADE.ts_utc + timedelta(seconds=1))
    other_qty = replace(CSV_TRADE, trade_id="x", qty=0.2)
    assert insert_trades(db, [API_TRADE, other_second, other_qty]) == 3
    assert insert_trades(db, [API_TRADE]) == 0  # mesma fonte: INSERT OR IGNORE pelo id


async def test_trade_of_coin_sold_between_syncs_is_fetched(db):
    c = FakeClient("binance", [Holding("binance", "ARB", "spot", 100)])
    await sync_all(db, {"binance": c}, notify=_notifier([]), now=NOW)
    sale = Trade("binance", "2", "ARB", "sell", 100, 1.0, 0, NOW + timedelta(minutes=1), "api")
    c.holdings, c.trades = [], [sale]  # vendeu tudo: o ARB some do saldo
    await sync_all(db, {"binance": c}, notify=_notifier([]), now=NOW + timedelta(minutes=5))
    assert [tuple(r) for r in db.execute("SELECT side, qty FROM trades WHERE symbol='ARB'")] == [("sell", 100)]


async def test_sync_fetches_symbols_already_in_trades(db):
    db.execute("INSERT INTO trades VALUES ('binance','c1','SOL','buy',1,100,0,'2025-01-01T00:00:00+00:00','csv')")
    c = FakeClient("binance", [Holding("binance", "BTC", "spot", 1)])
    await sync_all(db, {"binance": c}, notify=_notifier([]), now=NOW)
    assert set(c.asked) == {"BTC", "SOL"}

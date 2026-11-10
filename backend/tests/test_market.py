import json
from datetime import date
from pathlib import Path

import httpx
import pytest

from quilate.config import load_settings
from quilate.exchanges.client import Candle
from quilate.market import sources as S
from quilate.market.collect import alt_season_index, collect_daily

FX = Path(__file__).parent / "fixtures" / "market"
DAY = date(2026, 11, 4)


def fx(name):
    return json.loads((FX / f"{name}.json").read_text())


def mock_all(mock, fail=()):
    def r(source, method, url, data):
        route = mock.route(method=method, url__regex=url)
        if source in fail:
            route.respond(500)
        else:
            route.respond(json=data)

    r("cg", "GET", r"https://api\.coingecko\.com/api/v3/coins/markets.*", fx("coingecko_markets"))
    r("cg", "GET", r"https://api\.coingecko\.com/api/v3/coins/[^/]+/market_chart.*", fx("coingecko_chart"))
    r("cg", "GET", r"https://api\.coingecko\.com/api/v3/global.*", fx("coingecko_global"))
    r("fng", "GET", r"https://api\.alternative\.me/fng/.*", fx("fng"))
    r("defillama", "GET", r"https://stablecoins\.llama\.fi/stablecoins.*", fx("defillama"))
    for k in ("mvrv", "nupl", "sopr"):
        r("bgeometrics", "GET", rf"https://bitcoin-data\.com/v1/{k}/last", fx(f"bgeometrics_{k}"))
    r("coinalyze", "GET", r"https://api\.coinalyze\.net/v1/funding-rate.*", fx("coinalyze_funding"))
    r("coinalyze", "GET", r"https://api\.coinalyze\.net/v1/open-interest.*", fx("coinalyze_oi"))
    r("coinalyze", "GET", r"https://api\.coinalyze\.net/v1/liquidation-history.*", fx("coinalyze_liq"))
    r("fred", "GET", r"https://api\.stlouisfed\.org/fred/series/observations.*", fx("fred"))
    r("tftc", "GET", re_url(S.TFTC_URL), fx("tftc_etf"))
    r("binance_products", "GET", re_url(S.BINANCE_PRODUCTS_URL) + ".*", fx("binance_products"))


def re_url(u):
    import re
    return re.escape(u)


class FakeEx:
    def __init__(self, bases):
        self.markets = {f"{b}/USDT": {"base": b, "active": True, "spot": True} for b in bases}

    async def load_markets(self):
        return self.markets


class FakeClient:
    def __init__(self, name, bases):
        self.name, self.ex = name, FakeEx(bases)

    async def fetch_daily_candles(self, symbol, quote, days):
        return [Candle(date(2026, 11, 3), 1, 2, 0.5, 1.5, 1000.0)]


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    async def nop(_):
        pass

    monkeypatch.setattr(S, "_pause", nop)


@pytest.fixture
def keys(memory_keyring):
    for k in ("coingecko_key", "coinalyze_key", "fred_key"):
        memory_keyring.set_password("quilate", k, "k")


async def test_parsers_read_fixtures(respx_mock, keys):
    mock_all(respx_mock)
    async with httpx.AsyncClient() as http:
        assert 0 <= await S.fear_greed(http) <= 100
        assert (await S.coingecko_global(http))["btc_dominance"] > 0
        assets = await S.coingecko_assets(http)
        assert assets["BTC"] == S.AssetInfo("bitcoin", "BTC", "Bitcoin", 1)
        mk = await S.coingecko_markets(http, ["bitcoin"])
        assert mk["bitcoin"].price > 0 and mk["bitcoin"].circulating_supply > 0
        ch = await S.coingecko_chart(http, "bitcoin", 3)
        assert len(ch.prices) == len(ch.market_caps) == 4
        assert await S.defillama_stablecoins(http) > 0
        assert (await S.bgeometrics_btc(http)) == {"mvrv": 1.5036, "nupl": 0.3349, "sopr": 1.0032}
        assert await S.fred_latest(http, "DTWEXBGS") == 121.37  # pula o "." do dia sem dado
        assert (await S.tftc_etf_flows(http))[0] == {"day": "2026-10-29", "net_usd": 120500000.0}
        d = await S.coinalyze_derivs(http, ["BTC", "ETH"])
        assert d["BTC"] == S.Derivs(0.0001, 5.1e9, 4.6e6)


async def test_coingecko_key_sent_as_header(respx_mock, memory_keyring):
    memory_keyring.set_password("quilate", "coingecko_key", "abc")
    route = respx_mock.get(url__regex=r".*/global").respond(json=fx("coingecko_global"))
    async with httpx.AsyncClient() as http:
        await S.coingecko_global(http)
    assert route.calls[0].request.headers["x-cg-demo-api-key"] == "abc"


async def test_delisting_flags(respx_mock):
    mock_all(respx_mock)
    clients = {"binance": FakeClient("binance", ["BTC", "AVA"]), "mexc": FakeClient("mexc", ["BTC"])}
    async with httpx.AsyncClient() as http:
        out = await S.delisting_flags(http, clients, ["BTC", "AVA", "ZZZ"])
    assert out["BTC"] == S.DelistInfo(False, 2)
    assert out["AVA"] == S.DelistInfo(True, 1)
    assert out["ZZZ"] == S.DelistInfo(False, 0)


async def test_delisting_without_source_is_none(respx_mock):
    mock_all(respx_mock, fail={"binance_products"})
    async with httpx.AsyncClient() as http:
        out = await S.delisting_flags(http, {}, ["BTC"])
    assert out["BTC"] == S.DelistInfo(None, 0)


async def test_one_source_down_others_saved(db, respx_mock, keys):
    mock_all(respx_mock, fail={"bgeometrics"})
    db.execute("INSERT INTO positions VALUES ('binance','ETH','spot',1,'2026-11-04',0)")
    clients = {"binance": FakeClient("binance", ["BTC", "ETH"]), "mexc": FakeClient("mexc", ["ETH"])}
    async with httpx.AsyncClient() as http:
        rep = await collect_daily(db, http, clients, load_settings(), DAY)
    assert "bgeometrics" in rep.failed and "fng" in rep.ok
    assert set(rep.ok) >= {"cg_assets", "cg_markets", "cg_global", "derivs", "dxy", "usdbrl", "etf_flows",
                           "stablecoins", "alt_season", "delisting", "inflation", "candles"}
    keys_saved = {r[0] for r in db.execute("SELECT key FROM snapshots WHERE day='2026-11-04'")}
    assert {"fng", "cg_assets", "inflation", "alt_season", "usdbrl"} <= keys_saved and "btc_onchain" not in keys_saved
    assert any("series_id=DEXBZUS" in str(c.request.url) for c in respx_mock.calls)  # BRL por 1 USD
    assert json.loads(db.execute("SELECT value_json FROM snapshots WHERE key='cg_assets'").fetchone()[0])["BTC"]["rank"] == 1
    venues = {r[0] for r in db.execute("SELECT venue FROM candles WHERE symbol='ETH'")}
    assert venues == {"binance", "mexc"}


async def test_failing_cg_does_not_stop_fng(db, respx_mock, keys):
    mock_all(respx_mock, fail={"cg"})
    async with httpx.AsyncClient() as http:
        rep = await collect_daily(db, http, {}, load_settings(), DAY)
    assert "fng" in rep.ok and "cg_assets" in rep.failed and "alt_season" in rep.failed


def test_alt_season_index():
    assert alt_season_index(alt_90d=[0.5] * 40 + [-0.1] * 10, btc_90d=0.1) == 80


async def test_fred_error_does_not_leak_key(db, respx_mock, memory_keyring, caplog):
    import logging
    caplog.set_level(logging.INFO)
    for k in ("coingecko_key", "coinalyze_key", "fred_key"):
        memory_keyring.set_password("quilate", k, "SECRETFRED")
    mock_all(respx_mock, fail={"fred"})
    async with httpx.AsyncClient() as http:
        rep = await collect_daily(db, http, {}, load_settings(), DAY)
    assert "dxy" in rep.failed and "SECRETFRED" not in rep.failed["dxy"]
    assert "usdbrl" in rep.failed and "SECRETFRED" not in rep.failed["usdbrl"]
    assert "SECRETFRED" not in caplog.text


def test_mask_hides_keys():
    from quilate.market.collect import _mask
    assert "abc" not in _mask("GET https://x/y?api_key=abc&z=1") and "abc" not in _mask("x-cg-demo-api-key: abc")


async def test_one_exchange_candles_failure_isolated(db, respx_mock, keys):
    mock_all(respx_mock)
    db.execute("INSERT INTO positions VALUES ('binance','ETH','spot',1,'2026-11-04',0)")

    class Boom(FakeClient):
        async def fetch_daily_candles(self, *a):
            raise RuntimeError("falhou")

    clients = {"binance": Boom("binance", ["ETH"]), "mexc": FakeClient("mexc", ["ETH"])}
    async with httpx.AsyncClient() as http:
        rep = await collect_daily(db, http, clients, load_settings(), DAY)
    assert "candles:binance:ETH" in rep.failed and "candles" not in rep.ok
    assert {r[0] for r in db.execute("SELECT venue FROM candles")} == {"mexc"}


async def test_alt_season_skips_failing_chart(db, respx_mock, keys):
    mock_all(respx_mock)
    respx_mock.get(url__regex=r".*/coins/ethereum/market_chart.*").respond(500)
    async with httpx.AsyncClient() as http:
        rep = await collect_daily(db, http, {}, load_settings(), DAY)
    assert "alt_season" in rep.ok


async def test_bgeometrics_skipped_when_already_collected(db, respx_mock, keys):
    mock_all(respx_mock)
    db.execute("""INSERT INTO snapshots VALUES ('2026-11-04','btc_onchain','{"mvrv": 9}')""")
    async with httpx.AsyncClient() as http:
        rep = await collect_daily(db, http, {}, load_settings(), DAY)
    assert "bgeometrics" in rep.ok
    assert not [c for c in respx_mock.calls if "bitcoin-data.com" in str(c.request.url)]
    assert db.execute("SELECT value_json FROM snapshots WHERE key='btc_onchain'").fetchone()[0] == '{"mvrv": 9}'

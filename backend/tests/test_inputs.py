import json
from datetime import date, timedelta

from quilate.signals.inputs import build_inputs, dominance_7d_change

DAY = date(2026, 11, 4)


def seed_candles(db, symbol, closes, venue="binance", vol=10.0):
    for i, c in enumerate(closes):
        d = (DAY - timedelta(days=len(closes) - 1 - i)).isoformat()
        db.execute("INSERT INTO candles VALUES (?,?,?,?,?,?,?,?,?)", (venue, symbol, "USDT", d, c, c, c, c, vol))


def snap(db, key, value, day=DAY):
    db.execute("INSERT OR REPLACE INTO snapshots VALUES (?,?,?)", (day.isoformat(), key, json.dumps(value)))


def mention(db, symbol, days_ago, analyst, stance=None, polarity=None):
    d = (DAY - timedelta(days=days_ago)).isoformat() + "T12:00:00+00:00"
    db.execute("INSERT INTO mentions (msg_id, symbol, is_analyst, stance, polarity, date_utc) VALUES (1,?,?,?,?,?)",
               (symbol, analyst, stance, polarity, d))


def test_prices_volume_and_alt_btc(db):
    seed_candles(db, "BTC", [100.0, 100.0, 200.0])
    seed_candles(db, "ETH", [10.0, 20.0, 40.0], vol=5.0)
    seed_candles(db, "ETH", [11.0, 21.0, 41.0], venue="bybit", vol=3.0)  # Binance ganha no preço; volume soma
    i = build_inputs(db, "ETH", DAY, 500.0, 0.002, 4)
    assert i.usd_closes == [10.0, 20.0, 40.0]
    assert i.alt_btc_closes == [0.1, 0.2, 0.2]
    assert i.daily_volume_usd == [8.0, 8.0, 8.0]
    assert (i.is_btc, i.position_usd, i.spread_pct, i.listed_on) == (False, 500.0, 0.002, 4)


def test_falls_back_to_other_venue_and_btc_has_no_ratio(db):
    seed_candles(db, "BTC", [100.0, 110.0], venue="kraken")
    i = build_inputs(db, "BTC", DAY, 1.0, None, 3)
    assert i.is_btc and i.usd_closes == [100.0, 110.0] and i.alt_btc_closes == []


def test_snapshots(db):
    snap(db, "cg_assets", {"ETH": {"coingecko_id": "ethereum", "name": "Ethereum", "rank": 2}})
    snap(db, "cg_markets", {"ethereum": {"price": 1, "market_cap": 1, "volume_24h": 1, "ath": 4900.0,
                                         "circulating_supply": 1}})
    snap(db, "inflation", {"ETH": {"inflation_12m": 0.04, "unlock_90d": None}}, DAY - timedelta(days=1))
    snap(db, "delisting", {"ETH": {"monitoring_tag": True, "listed_on": 2}})
    i = build_inputs(db, "ETH", DAY, 1.0, None, 2)
    assert (i.ath_usd, i.inflation_yr_pct, i.unlock_90d_pct, i.monitoring_tag) == (4900.0, 0.04, None, True)
    empty = build_inputs(db, "SOL", DAY, 1.0, None, 2)
    assert (empty.ath_usd, empty.inflation_yr_pct, empty.monitoring_tag) == (None, None, None)


def test_mentions(db):
    mention(db, "ETH", 120, 1, "comprar")
    mention(db, "ETH", 104, 1, "manter")
    mention(db, "ETH", 104, 1, None)  # sem posição: conta para o silêncio, não para a posição
    mention(db, "ETH", 3, 0)
    mention(db, "ETH", 20, 0)
    mention(db, "ETH", 40, 0)
    i = build_inputs(db, "ETH", DAY, 1.0, None, 2)
    assert (i.analyst_stance, i.analyst_days) == ("manter", 104)
    assert (i.mentions_7d, i.mentions_30d) == (1, 2)
    assert i.group_polarity_7d is None  # menção do grupo sem polaridade gravada


def test_group_polarity_mean_of_last_7_days(db):
    mention(db, "ETH", 1, 0, polarity=1)
    mention(db, "ETH", 6, 0, polarity=0)
    mention(db, "ETH", 8, 0, polarity=-1)  # fora dos 7 dias
    mention(db, "ETH", 2, 1, polarity=-1)  # do analista: não é o grupo
    assert build_inputs(db, "ETH", DAY, 1.0, None, 2).group_polarity_7d == 0.5


def test_no_analyst_mention(db):
    mention(db, "ETH", 2, 0)
    i = build_inputs(db, "ETH", DAY, 1.0, None, 2)
    assert (i.analyst_stance, i.analyst_days) == (None, None)


def test_most_recent_stance_ignores_newer_null(db):
    mention(db, "ETH", 50, 1, "manter")
    mention(db, "ETH", 5, 1, None)
    i = build_inputs(db, "ETH", DAY, 1.0, None, 2)
    assert (i.analyst_stance, i.analyst_days) == ("manter", 5)


def test_dominance_7d_change(db):
    assert dominance_7d_change(db, DAY) is None
    for k in range(6):
        snap(db, "cg_global", {"btc_dominance": 50.0 + k}, DAY - timedelta(days=6 - k))
    assert dominance_7d_change(db, DAY) is None  # só 6 snapshots
    snap(db, "cg_global", {"btc_dominance": 57.0})
    assert dominance_7d_change(db, DAY) == 7.0


def test_snapshot_older_than_7_days_is_no_data(db):
    old = DAY - timedelta(days=8)
    snap(db, "cg_assets", {"ARB": {"coingecko_id": "arbitrum"}}, day=old)  # mapa de ids: sem limite de idade
    snap(db, "cg_markets", {"arbitrum": {"ath": 2.4}}, day=old)
    snap(db, "inflation", {"ARB": {"unlock_90d": 0.05, "inflation_12m": 0.2}}, day=old)
    snap(db, "delisting", {"ARB": {"monitoring_tag": True, "listed_on": 1}}, day=old)
    i = build_inputs(db, "ARB", DAY, 1.0, None, 3)
    assert (i.ath_usd, i.unlock_90d_pct, i.inflation_yr_pct, i.monitoring_tag) == (None, None, None, None)
    snap(db, "inflation", {"ARB": {"unlock_90d": 0.05, "inflation_12m": 0.2}}, day=DAY - timedelta(days=7))
    assert build_inputs(db, "ARB", DAY, 1.0, None, 3).unlock_90d_pct == 0.05  # 7 dias ainda vale

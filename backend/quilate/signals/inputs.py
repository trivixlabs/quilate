"""Lê candles, snapshots e menções do banco e monta os dados de um ativo para a régua."""
import json
import sqlite3
from datetime import date, timedelta

from quilate.signals.rubric import CoinInputs

MAX_AGE_DAYS = 7  # snapshot mais velho que isso (coleta parada) vira "sem dado" na régua e no veredito


def snapshot(conn: sqlite3.Connection, key: str, day: date, max_age_days: int | None = None):
    """Último snapshot da chave até `day`, ou None. Com `max_age_days`, só vale se tiver no máximo essa idade."""
    floor = (day - timedelta(days=max_age_days)).isoformat() if max_age_days is not None else ""
    row = conn.execute("SELECT value_json FROM snapshots WHERE key=? AND day<=? AND day>=? ORDER BY day DESC LIMIT 1",
                       (key, day.isoformat(), floor)).fetchone()
    return json.loads(row[0]) if row else None


def daily_closes(conn: sqlite3.Connection, symbol: str, day: date) -> dict[str, float]:
    """Um fechamento em USDT por dia: o da Binance, ou o de qualquer outra corretora."""
    out: dict[str, float] = {}
    for d, close in conn.execute(
            "SELECT day, close FROM candles WHERE symbol=? AND quote='USDT' AND day<=? AND close IS NOT NULL "
            "ORDER BY day, venue='binance' DESC, venue", (symbol, day.isoformat())):
        out.setdefault(d, close)
    return out


def dominance_7d_change(conn: sqlite3.Connection, day: date) -> float | None:
    """Dominância do BTC em `day` menos a de 6 dias antes. None sem os 7 snapshots diários."""
    days = [(day - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    rows = dict(conn.execute(
        f"SELECT day, value_json FROM snapshots WHERE key='cg_global' AND day IN ({','.join('?' * 7)})", days))
    if len(rows) < 7:
        return None
    return json.loads(rows[days[-1]])["btc_dominance"] - json.loads(rows[days[0]])["btc_dominance"]


def build_inputs(conn: sqlite3.Connection, symbol: str, day: date, position_usd: float,
                 spread_pct: float | None, listed_on: int) -> CoinInputs:
    usd = daily_closes(conn, symbol, day)
    btc = daily_closes(conn, "BTC", day)
    alt_btc = [usd[d] / btc[d] for d in sorted(usd.keys() & btc.keys()) if btc[d]]
    volume = [v for (v,) in conn.execute(
        "SELECT SUM(volume_quote) FROM candles WHERE symbol=? AND quote='USDT' AND day<=? "
        "GROUP BY day ORDER BY day", (symbol, day.isoformat())) if v is not None]

    assets = snapshot(conn, "cg_assets", day) or {}  # mapa símbolo -> id da CoinGecko: não envelhece
    markets = snapshot(conn, "cg_markets", day, MAX_AGE_DAYS) or {}
    ath = (markets.get((assets.get(symbol) or {}).get("coingecko_id")) or {}).get("ath")
    infl = (snapshot(conn, "inflation", day, MAX_AGE_DAYS) or {}).get(symbol) or {}
    delist = (snapshot(conn, "delisting", day, MAX_AGE_DAYS) or {}).get(symbol) or {}

    iso = day.isoformat()
    stance = conn.execute(
        "SELECT stance FROM mentions WHERE symbol=? AND is_analyst=1 AND stance IS NOT NULL AND date(date_utc)<=? "
        "ORDER BY date_utc DESC LIMIT 1", (symbol, iso)).fetchone()
    last = conn.execute("SELECT MAX(date(date_utc)) FROM mentions WHERE symbol=? AND is_analyst=1 "
                        "AND date(date_utc)<=?", (symbol, iso)).fetchone()[0]

    def count(days: int) -> int:
        since = (day - timedelta(days=days - 1)).isoformat()
        return conn.execute("SELECT COUNT(*) FROM mentions WHERE symbol=? AND date(date_utc) BETWEEN ? AND ?",
                            (symbol, since, iso)).fetchone()[0]

    return CoinInputs(
        symbol=symbol, is_btc=symbol == "BTC",
        alt_btc_closes=[] if symbol == "BTC" else alt_btc,
        usd_closes=[usd[d] for d in sorted(usd)], ath_usd=ath,
        daily_volume_usd=volume, position_usd=position_usd, spread_pct=spread_pct,
        unlock_90d_pct=infl.get("unlock_90d"), inflation_yr_pct=infl.get("inflation_12m"),
        monitoring_tag=delist.get("monitoring_tag"), listed_on=listed_on,
        analyst_stance=stance[0] if stance else None,
        analyst_days=(day - date.fromisoformat(last)).days if last else None,
        mentions_7d=count(7), mentions_30d=count(30),
        group_polarity_7d=conn.execute(
            "SELECT AVG(polarity) FROM mentions WHERE symbol=? AND is_analyst=0 AND polarity IS NOT NULL "
            "AND date(date_utc) BETWEEN ? AND ?", (symbol, (day - timedelta(days=6)).isoformat(), iso)).fetchone()[0])

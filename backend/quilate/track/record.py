"""Registro de acertos: compara cada veredito com o que o preço fez 7, 30 e 90 dias depois."""
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

from quilate.signals.inputs import daily_closes

HORIZONS = (7, 30, 90)


@dataclass(frozen=True)
class Outcome:
    verdict_id: int
    symbol: str
    verdict: str
    horizon: int
    r_hold: float   # retorno de segurar a moeda
    r_paper: float  # retorno se o veredito fosse seguido
    r_btc: float    # retorno do BTC no mesmo período
    hit: bool
    alerts: tuple[str, ...] = ()  # códigos dos sinais em alerta no veredito (S1..S7)


def paper_return(verdict: str, r_hold: float, fee: float = 0.002) -> float:
    """Manter segura tudo. Reduzir vende metade (paga metade da taxa). Sair vende tudo (paga a taxa)."""
    if verdict == "Reduzir":
        return 0.5 * r_hold - fee / 2
    if verdict == "Sair":
        return -fee
    return r_hold


def is_hit(verdict: str, r_hold: float, r_btc: float, fee: float = 0.002) -> bool:
    """Reduzir e Sair acertam se o retorno seguido supera o de segurar. Manter acerta se segurar vale mais que BTC."""
    if verdict == "Manter":
        return r_hold >= r_btc - fee
    return paper_return(verdict, r_hold, fee) > r_hold


def outcomes(conn: sqlite3.Connection, today: date) -> list[Outcome]:
    """Resultados por veredito e horizonte. Usa o último veredito do dia de cada moeda (final_verdict).

    Pula o horizonte sem candle no dia (veredito + horizonte) ou sem candle do BTC no dia do veredito.
    """
    rows = conn.execute(
        "SELECT id, day, symbol, final_verdict, price_usd, signals_json FROM verdicts v "
        "WHERE created_utc = (SELECT MAX(created_utc) FROM verdicts WHERE day=v.day AND symbol=v.symbol) "
        "AND id = (SELECT MAX(id) FROM verdicts WHERE day=v.day AND symbol=v.symbol AND created_utc=v.created_utc) "
        "ORDER BY day, symbol").fetchall()
    closes: dict[str, dict[str, float]] = {}

    def close(symbol: str, day: str) -> float | None:
        if symbol not in closes:
            closes[symbol] = daily_closes(conn, symbol, today)
        return closes[symbol].get(day)

    out = []
    for vid, day, symbol, verdict, price, sig_json in rows:
        alerts = tuple(s["code"] for s in json.loads(sig_json) if s["alert"])
        btc0 = close("BTC", day)
        for h in HORIZONS:
            end = (date.fromisoformat(day) + timedelta(days=h)).isoformat()
            p1, btc1 = close(symbol, end), close("BTC", end)
            if not (price and btc0 and p1 and btc1):
                continue
            r_hold, r_btc = p1 / price - 1, btc1 / btc0 - 1
            out.append(Outcome(vid, symbol, verdict, h, r_hold, paper_return(verdict, r_hold), r_btc,
                               is_hit(verdict, r_hold, r_btc), alerts))
    return out


def hit_rates(outs: list[Outcome]) -> dict:
    """Taxa de acerto por veredito e por sinal.

    Formato (serializável em JSON na Task 18, onde a chave do horizonte vira texto):
    {"by_verdict": {"Manter"|"Reduzir"|"Sair": {7|30|90: {"n": int, "hits": int, "rate": float}}},
     "by_signal": {"S1".."S7": {7|30|90: {...}}}}  # só vereditos com o sinal em alerta
    Combinações sem amostra ficam ausentes.
    Manter do BTC fica fora das taxas: o BTC é a própria referência (r_btc == r_hold), então acertaria sempre.
    Reduzir e Sair do BTC contam normalmente.
    """
    def add(bucket: dict, o: Outcome) -> None:
        c = bucket.setdefault(o.horizon, {"n": 0, "hits": 0, "rate": 0.0})
        c["n"] += 1
        c["hits"] += o.hit
        c["rate"] = c["hits"] / c["n"]

    res: dict = {"by_verdict": {}, "by_signal": {f"S{i}": {} for i in range(1, 8)}}
    for o in outs:
        if o.symbol == "BTC" and o.verdict == "Manter":
            continue
        add(res["by_verdict"].setdefault(o.verdict, {}), o)
        for code in o.alerts:
            if code in res["by_signal"]:
                add(res["by_signal"][code], o)
    return res

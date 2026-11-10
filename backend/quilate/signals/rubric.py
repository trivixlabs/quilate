"""Os 7 sinais da régua e o veredito. Funções puras, sem acesso a banco.

Percentuais em CoinInputs (spread, desbloqueio, inflação) são frações: 0,03 = 3%.
"""
from dataclasses import dataclass
from statistics import mean
from typing import Literal

from quilate.config import Thresholds

NO_DATA = "sem dado"
MA_DAYS = 200
ALT_SEASON_MAX = 25


@dataclass
class CoinInputs:
    symbol: str
    is_btc: bool
    alt_btc_closes: list[float]
    usd_closes: list[float]
    ath_usd: float | None
    daily_volume_usd: list[float]
    position_usd: float
    spread_pct: float | None
    unlock_90d_pct: float | None
    inflation_yr_pct: float | None
    monitoring_tag: bool | None
    listed_on: int
    analyst_stance: str | None
    analyst_days: int | None
    mentions_7d: int
    mentions_30d: int
    group_polarity_7d: float | None = None  # média de -1 a 1 das menções do grupo em 7 dias; None sem menção


@dataclass
class SignalResult:
    code: str
    name: str
    alert: bool | None  # None = sem dado
    value: str


def fmt_num(x: float, decimals: int = 0) -> str:
    return f"{x:,.{decimals}f}".replace(",", "_").replace(".", ",").replace("_", ".")


def _pct(x: float, decimals: int = 0) -> str:
    return fmt_num(abs(x) * 100, decimals) if x >= 0 else "−" + fmt_num(abs(x) * 100, decimals)


def _r(code: str, name: str, alert: bool | None, value: str = NO_DATA) -> SignalResult:
    return SignalResult(code, name, alert, value if alert is not None else NO_DATA)


def _below_ma(closes: list[float]) -> bool:
    return closes[-1] < mean(closes[-MA_DAYS:])


def s1(inp: CoinInputs, th: Thresholds) -> SignalResult:
    c = inp.alt_btc_closes
    if inp.is_btc or len(c) < MA_DAYS:
        return _r("S1", "Força contra o BTC", None)
    ret = c[-1] / c[-91] - 1
    return _r("S1", "Força contra o BTC", ret < th.s1_ret_90d and _below_ma(c), f"{_pct(ret)}% em 90 d")


def s2(inp: CoinInputs, th: Thresholds) -> SignalResult:
    c = inp.usd_closes
    if len(c) < MA_DAYS or not inp.ath_usd:
        return _r("S2", "Tendência de queda", None)
    drawdown = 1 - c[-1] / inp.ath_usd
    higher_low = min(c[-90:]) > min(c[-180:-90])
    alert = _below_ma(c) and drawdown > th.s2_drawdown and not higher_low
    return _r("S2", "Tendência de queda", alert, f"−{_pct(drawdown)}% da máxima")


def s3(inp: CoinInputs, th: Thresholds) -> SignalResult:
    v = inp.daily_volume_usd
    checks: list[bool] = []
    parts: list[str] = []
    if len(v) >= 180 and mean(v[-180:]) > 0:  # spec 8.4: média de 30 dias sobre a de 180
        ratio = mean(v[-30:]) / mean(v[-180:])
        checks.append(ratio < th.s3_vol_ratio)
        parts.append(f"volume {fmt_num(ratio, 2)}×")
    if len(v) >= 30:
        checks.append(mean(v[-30:]) < th.s3_pos_mult * inp.position_usd)
    if inp.spread_pct is not None:
        checks.append(inp.spread_pct > th.s3_spread)
        parts.append(f"spread {_pct(inp.spread_pct, 2)}%")
    return _r("S3", "Liquidez", any(checks) if checks else None, ", ".join(parts))


def s4(inp: CoinInputs, th: Thresholds) -> SignalResult:
    u, i = inp.unlock_90d_pct, inp.inflation_yr_pct
    if u is None and i is None:
        return _r("S4", "Oferta nova", None)
    alert = (u is not None and u > th.s4_unlock_90d) or (i is not None and i > th.s4_inflation)
    if u is not None and (i is None or u > th.s4_unlock_90d or i <= th.s4_inflation):
        value = f"{_pct(u, 2)}% em 90 d"
    else:
        value = f"inflação {_pct(i, 2)}% ao ano"
    return _r("S4", "Oferta nova", alert, value)


def s5(inp: CoinInputs, th: Thresholds) -> SignalResult:
    if inp.monitoring_tag is None and inp.listed_on == 0:  # sem snapshot de deslistagem
        return _r("S5", "Risco de deslistagem", None)
    alert = inp.monitoring_tag is True or inp.listed_on == 1
    value = "Monitoring Tag" if inp.monitoring_tag else f"em {inp.listed_on} corretora(s)"
    return _r("S5", "Risco de deslistagem", alert, value)


def s6(inp: CoinInputs, th: Thresholds) -> SignalResult:
    if inp.analyst_stance is None or inp.analyst_days is None:
        return _r("S6", "Analista", None)
    if inp.analyst_stance == "sair":
        return _r("S6", "Analista", True, "mandou sair")
    return _r("S6", "Analista", inp.analyst_days > th.s6_silence_days, f"silêncio {inp.analyst_days} d")


def s7(inp: CoinInputs, th: Thresholds) -> SignalResult:
    if inp.mentions_30d == 0:
        return _r("S7", "Atenção do grupo", None)
    ratio = inp.mentions_7d / (inp.mentions_30d / 30 * 7)
    c = inp.usd_closes
    near_high = bool(c) and c[-1] >= th.s7_near_high * max(c[-90:])
    pol = inp.group_polarity_7d
    # euforia é falatório positivo perto da máxima; grupo falando mal da moeda não é euforia
    euphoria = ratio > th.s7_high and near_high and (pol is None or pol > 0)
    alert = ratio < th.s7_low or euphoria
    value = f"menções {fmt_num(ratio, 1)}× a média" + ("" if pol is None else f", polaridade {pol:+.1f}".replace(".", ","))
    return _r("S7", "Atenção do grupo", alert, value)


def compute_signals(inp: CoinInputs, th: Thresholds) -> list[SignalResult]:
    return [f(inp, th) for f in (s1, s2, s3, s4, s5, s6, s7)]


def market_filter(dominance_7d_change: float | None, alt_season: int | None) -> int:
    """1 ponto quando a dominância do BTC sobe e a altseason está abaixo de 25."""
    if dominance_7d_change is None or alt_season is None:
        return 0
    return int(dominance_7d_change > 0 and alt_season < ALT_SEASON_MAX)


def rubric_verdict(signals: list[SignalResult], filter_points: int,
                   is_btc: bool) -> Literal["Manter", "Reduzir", "Sair"]:
    total = sum(s.alert is True for s in signals) + (0 if is_btc else filter_points)
    return "Sair" if total >= 5 else "Reduzir" if total >= 3 else "Manter"

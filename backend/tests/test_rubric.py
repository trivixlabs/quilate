import pytest

from quilate.config import Thresholds
from quilate.signals.rubric import CoinInputs, SignalResult, compute_signals, market_filter, rubric_verdict, s1, s2, s3, s4, s5, s6, s7

TH = Thresholds(s1_ret_90d=-0.20, s2_drawdown=0.85, s3_vol_ratio=0.5, s3_pos_mult=20, s3_spread=0.01,
                s4_unlock_90d=0.03, s4_inflation=0.10, s6_silence_days=90, s7_low=0.3, s7_high=3.0,
                s7_near_high=0.9)


def inputs(**kw) -> CoinInputs:
    base = dict(symbol="ETH", is_btc=False, alt_btc_closes=[1.0] * 250, usd_closes=[100.0] * 250, ath_usd=100.0,
                daily_volume_usd=[1e6] * 60, position_usd=1000.0, spread_pct=0.001, unlock_90d_pct=0.0,
                inflation_yr_pct=0.0, monitoring_tag=False, listed_on=3, analyst_stance="manter", analyst_days=5,
                mentions_7d=7, mentions_30d=30)
    base.update(kw)
    return CoinInputs(**base)


def closes_ret(ret: float, below_ma: bool) -> list[float]:
    """250 fechamentos: há 90 dias vale 1, o último vale 1+ret; o início alto ou baixo põe a MM200 acima ou abaixo."""
    filler = 10.0 if below_ma else 0.1
    return [filler] * 159 + [1.0] * 90 + [1 + ret]


def test_s1_borders():
    assert s1(inputs(alt_btc_closes=closes_ret(-0.21, True)), TH).alert is True
    assert s1(inputs(alt_btc_closes=closes_ret(-0.19, True)), TH).alert is False
    assert s1(inputs(alt_btc_closes=closes_ret(-0.30, False)), TH).alert is False


def test_s1_value():
    assert s1(inputs(alt_btc_closes=closes_ret(-0.34, True)), TH).value == "−34% em 90 d"


def test_s1_btc_and_short_history_have_no_data():
    r = compute_signals(inputs(symbol="BTC", is_btc=True), TH)
    assert len(r) == 7 and [x.code for x in r] == [f"S{i}" for i in range(1, 8)]
    assert r[0].alert is None and r[0].value == "sem dado"
    assert s1(inputs(alt_btc_closes=[1.0] * 199), TH).alert is None


def s2_closes(last: float, low_recent: float, low_old: float) -> list[float]:
    s = [100.0] * 250
    s[-1] = last
    s[-50] = low_recent
    s[-120] = low_old
    return s


def test_s2_needs_all_three():
    # ath 100, último 10 (queda 90% > 85%), MM200 acima, fundo recente 10 <= fundo antigo 10: sem fundo mais alto
    assert s2(inputs(usd_closes=s2_closes(10, 10, 10)), TH).alert is True
    assert s2(inputs(usd_closes=s2_closes(16, 16, 16)), TH).alert is False  # queda só de 84%
    assert s2(inputs(usd_closes=s2_closes(10, 10, 5)), TH).alert is False  # fundo mais alto: 10 > 5
    assert s2(inputs(usd_closes=[100.0] * 250, ath_usd=1000.0), TH).alert is False  # acima da MM200


def test_s2_no_data():
    assert s2(inputs(ath_usd=None), TH).alert is None
    assert s2(inputs(usd_closes=[1.0] * 100), TH).alert is None


def test_s3_any_condition():
    def vol(r30):  # 150 dias com 1e9 e 30 dias com r30*1e9: razão = r30 / ((150 + 30*r30) / 180)
        return inputs(daily_volume_usd=[1e9] * 150 + [r30 * 1e9] * 30)
    assert s3(vol(0.4), TH).alert is True    # razão 0,44
    assert s3(vol(0.55), TH).alert is False  # razão 0,59
    assert s3(vol(0.4), TH).value == "volume 0,44×, spread 0,10%"
    assert s3(inputs(daily_volume_usd=[1e6] * 30, position_usd=1e6 / 20 + 1), TH).alert is True  # volume < 20× posição
    assert s3(inputs(daily_volume_usd=[1e6] * 30, position_usd=1e6 / 20 - 1), TH).alert is False
    assert s3(inputs(spread_pct=0.0101), TH).alert is True
    assert s3(inputs(spread_pct=0.0099), TH).alert is False


def test_s3_ratio_needs_180_days():
    short = s3(inputs(daily_volume_usd=[1e9] * 149 + [1e8] * 30, spread_pct=None), TH)  # 179 dias
    assert short.alert is False and "volume" not in short.value  # razão 0,1 ignorada, só o teste da posição


def test_s3_no_data():
    assert s3(inputs(daily_volume_usd=[], spread_pct=None), TH).alert is None
    assert s3(inputs(daily_volume_usd=[], spread_pct=None), TH).value == "sem dado"


def test_s4():
    assert s4(inputs(unlock_90d_pct=0.0301), TH).alert is True
    assert s4(inputs(unlock_90d_pct=0.0299), TH).alert is False
    assert s4(inputs(inflation_yr_pct=0.1001), TH).alert is True
    assert s4(inputs(inflation_yr_pct=0.0999), TH).alert is False
    assert s4(inputs(unlock_90d_pct=None, inflation_yr_pct=None), TH).alert is None
    assert s4(inputs(unlock_90d_pct=0.0301), TH).value == "3,01% em 90 d"
    assert s4(inputs(unlock_90d_pct=None, inflation_yr_pct=0.1201), TH).alert is True


def test_s5():
    assert s5(inputs(monitoring_tag=True), TH).alert is True
    assert s5(inputs(listed_on=1), TH).alert is True
    assert s5(inputs(monitoring_tag=False, listed_on=2), TH).alert is False
    assert s5(inputs(monitoring_tag=None, listed_on=2), TH).alert is False
    unknown = s5(inputs(monitoring_tag=None, listed_on=0), TH)
    assert (unknown.alert, unknown.value) == (None, "sem dado")


def test_s6():
    assert s6(inputs(analyst_stance="sair", analyst_days=3), TH).alert is True
    assert s6(inputs(analyst_stance="manter", analyst_days=91), TH).alert is True
    assert s6(inputs(analyst_stance="manter", analyst_days=90), TH).alert is False
    assert s6(inputs(analyst_stance=None, analyst_days=None), TH).alert is None
    assert s6(inputs(analyst_stance="manter", analyst_days=104), TH).value == "silêncio 104 d"


def test_s7():
    assert s7(inputs(mentions_7d=2, mentions_30d=40), TH).alert is True  # 2 / 9,33 = 0,21
    near = [100.0] * 249 + [95.0]
    far = [100.0] * 249 + [80.0]
    assert s7(inputs(mentions_7d=40, mentions_30d=40, usd_closes=near), TH).alert is True  # 40 / 9,33 = 4,3
    assert s7(inputs(mentions_7d=40, mentions_30d=40, usd_closes=far), TH).alert is False
    assert s7(inputs(mentions_7d=7, mentions_30d=30), TH).alert is False
    assert s7(inputs(mentions_7d=0, mentions_30d=0), TH).alert is None
    # R38: polaridade do grupo. Falatório negativo perto da máxima não é euforia; desinteresse não olha polaridade
    assert s7(inputs(mentions_7d=40, mentions_30d=40, usd_closes=near, group_polarity_7d=-0.5), TH).alert is False
    pos = s7(inputs(mentions_7d=40, mentions_30d=40, usd_closes=near, group_polarity_7d=0.5), TH)
    assert pos.alert is True and pos.value == "menções 4,3× a média, polaridade +0,5"
    assert s7(inputs(mentions_7d=2, mentions_30d=40, group_polarity_7d=1.0), TH).alert is True


def fake_signals(alerts: int, none: int = 0) -> list[SignalResult]:
    out = []
    for i in range(7):
        a = True if i < alerts else (None if i < alerts + none else False)
        out.append(SignalResult(f"S{i + 1}", "x", a, "v"))
    return out


@pytest.mark.parametrize("alerts,expected", [(2, "Manter"), (3, "Reduzir"), (4, "Reduzir"), (5, "Sair")])
def test_sum_to_verdict(alerts, expected):
    assert rubric_verdict(fake_signals(alerts), 0, is_btc=False) == expected


def test_filter_adds_to_alts_not_btc():
    assert rubric_verdict(fake_signals(2), 1, is_btc=False) == "Reduzir"
    assert rubric_verdict(fake_signals(2), 1, is_btc=True) == "Manter"


def test_no_data_counts_zero():
    assert rubric_verdict(fake_signals(2, none=5), 0, is_btc=False) == "Manter"


def test_market_filter():
    assert market_filter(0.4, 20) == 1 and market_filter(-0.1, 20) == 0 and market_filter(0.4, None) == 0
    assert market_filter(0.4, 25) == 0 and market_filter(0.4, 24) == 1 and market_filter(0.0, 20) == 0
    assert market_filter(None, 20) == 0

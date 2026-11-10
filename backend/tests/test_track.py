import json
from datetime import date

import pytest

from quilate.track.record import Outcome, hit_rates, is_hit, outcomes, paper_return


def test_paper_returns():
    assert paper_return("Manter", 0.10) == pytest.approx(0.10)
    assert paper_return("Reduzir", 0.10) == pytest.approx(0.05 - 0.001)
    assert paper_return("Sair", -0.30) == pytest.approx(-0.002)


def test_hits():
    assert is_hit("Sair", r_hold=-0.30, r_btc=0.05) is True
    assert is_hit("Sair", r_hold=0.20, r_btc=0.05) is False
    assert is_hit("Manter", r_hold=0.06, r_btc=0.05) is True
    assert is_hit("Manter", r_hold=0.02, r_btc=0.05) is False


def _candle(db, venue, symbol, day, close):
    db.execute("INSERT INTO candles (venue, symbol, quote, day, close) VALUES (?,?,'USDT',?,?)",
               (venue, symbol, day, close))


def _verdict(db, day, symbol, final, price, created, alerts=()):
    sigs = [{"code": f"S{i}", "name": "x", "alert": i in alerts, "value": ""} for i in range(1, 8)]
    db.execute(
        "INSERT INTO verdicts (day, symbol, trigger, rubric_verdict, final_verdict, signals_json, pros_json,"
        " cons_json, main_risk, cited_json, price_usd, price_btc, created_utc) VALUES (?,?,?,?,?,?,'[]','[]','','[]',?,1,?)",
        (day, symbol, "diario", final, final, json.dumps(sigs), price, created))


def test_outcomes_skip_future_horizons(db):
    _verdict(db, "2026-10-30", "ETH", "Sair", 100.0, "2026-10-30T20:00:00")  # 5 dias atrás
    _candle(db, "binance", "BTC", "2026-10-30", 50.0)
    _candle(db, "binance", "ETH", "2026-11-04", 90.0)
    assert outcomes(db, date(2026, 11, 4)) == []


def test_outcomes_values_last_of_day_and_fallback_venue(db):
    _verdict(db, "2026-10-01", "ETH", "Manter", 100.0, "2026-10-01T08:00:00", alerts={1})
    _verdict(db, "2026-10-01", "ETH", "Sair", 100.0, "2026-10-01T20:00:00", alerts={1, 2})
    _candle(db, "binance", "BTC", "2026-10-01", 50.0)
    _candle(db, "binance", "BTC", "2026-10-08", 55.0)
    _candle(db, "kraken", "ETH", "2026-10-08", 80.0)  # sem Binance: usa outra corretora
    outs = outcomes(db, date(2026, 11, 4))
    assert len(outs) == 1
    o = outs[0]
    assert (o.symbol, o.verdict, o.horizon) == ("ETH", "Sair", 7)
    assert o.r_hold == pytest.approx(-0.2) and o.r_btc == pytest.approx(0.1)
    assert o.r_paper == pytest.approx(-0.002) and o.hit is True
    assert o.alerts == ("S1", "S2")


def test_hit_rates():
    def o(v, h, hit, alerts=()):
        return Outcome(1, "X", v, h, 0.0, 0.0, 0.0, hit, tuple(alerts))
    r = hit_rates([o("Sair", 7, True, ["S1"]), o("Sair", 7, False, ["S1", "S2"]), o("Manter", 30, True)])
    assert r["by_verdict"]["Sair"][7] == {"n": 2, "hits": 1, "rate": 0.5}
    assert r["by_verdict"]["Manter"][30] == {"n": 1, "hits": 1, "rate": 1.0}
    assert r["by_signal"]["S1"][7] == {"n": 2, "hits": 1, "rate": 0.5}
    assert r["by_signal"]["S2"][7] == {"n": 1, "hits": 0, "rate": 0.0}
    assert r["by_signal"]["S3"] == {}


def test_btc_manter_is_left_out_of_the_rates():
    # BTC contra ele mesmo: r_btc == r_hold, então Manter acertaria sempre
    outs = [Outcome(1, "BTC", "Manter", 7, -0.3, -0.3, -0.3, True, ("S1",)),
            Outcome(2, "ETH", "Manter", 7, -0.3, -0.3, 0.1, False, ("S1",)),
            Outcome(3, "BTC", "Sair", 7, -0.3, -0.002, -0.3, True)]
    r = hit_rates(outs)
    assert r["by_verdict"]["Manter"][7] == {"n": 1, "hits": 0, "rate": 0.0}
    assert r["by_signal"]["S1"][7]["n"] == 1
    assert r["by_verdict"]["Sair"][7]["n"] == 1  # Sair e Reduzir do BTC contam normalmente

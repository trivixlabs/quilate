from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from quilate.budget import budget_state, cost_usd, month_spent
from quilate.config import load_settings

NOW = datetime(2026, 6, 15, 12, tzinfo=UTC)


@pytest.fixture
def settings():
    return replace(load_settings(), budget_usd=50, budget_alert_ratio=0.8)  # sem depender do arquivo local


def Usage(**kw):
    return SimpleNamespace(**kw)


def add_cost(db, usd, one_time=False, ts="2026-06-10T12:00:00+00:00"):
    db.execute(
        "INSERT INTO api_costs (ts_utc, model, purpose, one_time, usd) VALUES (?,?,?,?,?)",
        (ts, "claude-sonnet-5-5", "t", int(one_time), usd),
    )


def test_cost_formula(settings):
    u = Usage(input_tokens=1000, output_tokens=500, cache_read_input_tokens=10_000, cache_creation_input_tokens=0)
    assert cost_usd("claude-sonnet-5-5", u, settings.prices) == pytest.approx(0.008)  # 2000 + 5000 + 1000 micro-dólares


def test_cache_write_uses_1h_price(settings):
    u = Usage(input_tokens=0, output_tokens=0, cache_read_input_tokens=None, cache_creation_input_tokens=1_000_000)
    assert cost_usd("claude-opus-5-5", u, settings.prices) == pytest.approx(8.0)


def test_official_price_table(settings):
    """R45: conferido na página oficial em 09/11/2026."""
    p = settings.prices
    assert (p["claude-sonnet-5-5"].cache_read, p["claude-opus-5-5"].cache_read, p["claude-haiku-5-5"].cache_read) == (0.10, 0.20, 0.01)


def test_haiku_long_prompt_pays_five_times(settings):
    short = SimpleNamespace(input_tokens=60_000, output_tokens=1_000, cache_read_input_tokens=40_000, cache_creation_input_tokens=0)
    long = SimpleNamespace(input_tokens=60_000, output_tokens=1_000, cache_read_input_tokens=40_001, cache_creation_input_tokens=0)
    base = (60_000 * 0.10 + 1_000 * 0.50 + 40_000 * 0.01) / 1e6
    assert cost_usd("claude-haiku-5-5", short, settings.prices) == pytest.approx(base)
    assert cost_usd("claude-haiku-5-5", long, settings.prices) == pytest.approx(5 * (base + 0.01 / 1e6))
    assert cost_usd("claude-sonnet-5-5", long, settings.prices) == pytest.approx((60_000 * 2 + 1_000 * 10 + 40_001 * 0.10) / 1e6)


def test_budget_states(db, settings):
    add_cost(db, 39.9)
    assert budget_state(db, settings, NOW) == "ok"
    add_cost(db, 0.2)
    assert budget_state(db, settings, NOW) == "alerta"
    add_cost(db, 10)
    assert budget_state(db, settings, NOW) == "bloqueado"


def test_one_time_costs_do_not_count(db, settings):
    add_cost(db, 100, one_time=True)
    assert month_spent(db, NOW, settings.tz) == 0


def test_month_boundary_uses_local_tz(db, settings):
    # 01/06 02:00 UTC ainda é 31/05 em São Paulo; 01/07 02:00 UTC já é 30/06 lá.
    add_cost(db, 1, ts="2026-06-01T02:00:00+00:00")
    add_cost(db, 2, ts="2026-07-01T02:00:00+00:00")
    add_cost(db, 4, ts="2026-06-01T04:00:00+00:00")
    assert month_spent(db, NOW, settings.tz) == pytest.approx(6)

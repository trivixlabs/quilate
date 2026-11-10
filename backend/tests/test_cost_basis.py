from datetime import UTC, datetime, timedelta
from itertools import count

import pytest

from quilate.exchanges.cost_basis import Trade, compute_cost_basis, unrealized_pnl

_n = count()


def _trade(side, qty, price, fee=0.0, symbol="BTC", exchange="binance"):
    i = next(_n)
    ts = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(minutes=i)
    return Trade(exchange, f"t{i}", symbol, side, qty, price, fee, ts, "api")


def buy(qty, price, fee=0.0, **kw):
    return _trade("buy", qty, price, fee, **kw)


def sell(qty, price, fee=0.0, **kw):
    return _trade("sell", qty, price, fee, **kw)


def test_weighted_average_with_sell():
    t = [buy(1, 100), buy(1, 200), sell(1, 300)]
    b = compute_cost_basis(t, held_qty=1, override_avg=None)
    assert b.avg_cost_usd == pytest.approx(150) and not b.unknown


def test_fees_raise_cost():
    b = compute_cost_basis([buy(2, 100, fee=2)], held_qty=2, override_avg=None)
    assert b.avg_cost_usd == pytest.approx(101)


def test_held_more_than_known_is_unknown():
    b = compute_cost_basis([buy(1, 100)], held_qty=2, override_avg=None)
    assert b.unknown and b.avg_cost_usd is None and unrealized_pnl(b, 120) is None


def test_override_wins():
    b = compute_cost_basis([], held_qty=5, override_avg=1.65)
    assert b.avg_cost_usd == 1.65 and not b.unknown


def test_no_trades_no_holding():
    assert compute_cost_basis([], held_qty=0, override_avg=None).avg_cost_usd is None


def test_trades_sorted_by_ts_and_exchanges_pooled():
    # fora de ordem e em duas corretoras: o custo médio é o mesmo
    a, b_, s = buy(1, 100, exchange="binance"), buy(1, 200, exchange="kraken"), sell(1, 300)
    r = compute_cost_basis([s, b_, a], held_qty=1, override_avg=None)
    assert r.avg_cost_usd == pytest.approx(150)


def test_unrealized_pnl():
    b = compute_cost_basis([buy(2, 100)], held_qty=2, override_avg=None)
    assert unrealized_pnl(b, 130) == pytest.approx(60)


def test_convert_pair_moves_cost_to_destination():
    # Convert: vende 1 ETH a US$ 300 e compra 3 SOL a US$ 100 (mesmo valor em USD)
    trades = [
        buy(1, 200, symbol="ETH"),
        sell(1, 300, symbol="ETH"),
        buy(3, 100, symbol="SOL"),
    ]
    eth = compute_cost_basis([t for t in trades if t.symbol == "ETH"], held_qty=0, override_avg=None)
    sol = compute_cost_basis([t for t in trades if t.symbol == "SOL"], held_qty=3, override_avg=None)
    assert eth.avg_cost_usd is None
    assert sol.avg_cost_usd == pytest.approx(100) and not sol.unknown

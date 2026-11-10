from dataclasses import dataclass
from datetime import datetime
from typing import Literal


@dataclass
class Trade:
    exchange: str
    trade_id: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    price_usd: float
    fee_usd: float
    ts_utc: datetime
    source: Literal["api", "csv", "manual"]


@dataclass
class CostBasis:
    held_qty: float
    known_qty: float
    avg_cost_usd: float | None
    unknown: bool


def compute_cost_basis(trades: list[Trade], held_qty: float, override_avg: float | None) -> CostBasis:
    """Preço médio ponderado de todas as corretoras juntas, em ordem de ts_utc."""
    qty = cost = 0.0
    for t in sorted(trades, key=lambda t: t.ts_utc):
        if t.side == "buy":
            qty += t.qty
            cost += t.qty * t.price_usd + t.fee_usd
        elif qty > 0:
            sold = min(t.qty, qty)
            cost -= cost / qty * sold
            qty -= sold
    if override_avg is not None:
        return CostBasis(held_qty, qty, override_avg, False)
    if held_qty > 0 and qty < 0.99 * held_qty:
        return CostBasis(held_qty, qty, None, True)
    return CostBasis(held_qty, qty, cost / qty if held_qty > 0 and qty > 0 else None, False)


def unrealized_pnl(basis: CostBasis, price_usd: float) -> float | None:
    if basis.avg_cost_usd is None:
        return None
    return (price_usd - basis.avg_cost_usd) * basis.held_qty

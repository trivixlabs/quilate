from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from quilate.config import ModelPrice, Settings


class BudgetExceeded(Exception):
    """Limite mensal atingido. O nome da classe é lido por knowledge/mentions.py."""


def cost_usd(model: str, usage, prices: dict[str, ModelPrice]) -> float:
    p = prices[model]
    read, write = usage.cache_read_input_tokens or 0, usage.cache_creation_input_tokens or 0
    # o tamanho do prompt conta a entrada inteira, com leitura e escrita de cache
    long = p.long_prompt_tokens is not None and usage.input_tokens + read + write > p.long_prompt_tokens
    usd = (usage.input_tokens * p.input + usage.output_tokens * p.output + read * p.cache_read + write * p.cache_write_1h) / 1_000_000
    return usd * (p.long_prompt_mult if long else 1.0)


def month_key(now: datetime, tz: str) -> str:
    return now.astimezone(ZoneInfo(tz)).strftime("%Y-%m")


def month_spent(conn, now: datetime, tz: str) -> float:
    local = now.astimezone(ZoneInfo(tz))
    start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = start.replace(year=start.year + (start.month == 12), month=start.month % 12 + 1)
    lo, hi = (d.astimezone(UTC).isoformat(timespec="seconds") for d in (start, nxt))
    row = conn.execute(
        "SELECT COALESCE(SUM(usd), 0) FROM api_costs WHERE one_time = 0 AND ts_utc >= ? AND ts_utc < ?", (lo, hi)
    ).fetchone()
    return row[0]


def budget_state(conn, settings: Settings, now: datetime) -> Literal["ok", "alerta", "bloqueado"]:
    spent = month_spent(conn, now, settings.tz)
    if spent >= settings.budget_usd:
        return "bloqueado"
    return "alerta" if spent >= settings.budget_usd * settings.budget_alert_ratio else "ok"

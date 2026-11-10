import logging
import sqlite3
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from quilate.budget import BudgetExceeded, budget_state, cost_usd, month_key, month_spent
from quilate.config import Settings
from quilate.secrets import get_secret

log = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = {"claude-sonnet-5-5", "claude-opus-5-5"}  # nunca o Haiku
NONSTREAM_MAX_TOKENS = 16_000  # acima disso o SDK exige streaming (pedido que pode passar de 10 min)

__all__ = ["BudgetExceeded", "Claude", "InvalidOutput", "Refused", "make_client"]


class Refused(Exception):
    def __init__(self, category: str | None):
        super().__init__(f"Claude recusou a resposta (categoria: {category})")
        self.category = category


class InvalidOutput(Exception):
    pass


def make_client() -> anthropic.AsyncAnthropic:
    return anthropic.AsyncAnthropic(api_key=get_secret("anthropic_api_key"))


class Claude:
    def __init__(self, client: anthropic.AsyncAnthropic, conn: sqlite3.Connection, settings: Settings,
                 notify: Callable[[str], Awaitable[None]], now: Callable[[], datetime] = lambda: datetime.now(UTC)):
        self.client, self.conn, self.settings, self.notify, self.now = client, conn, settings, notify, now

    async def parse(
        self, *, purpose: str, model: str, system: list[dict], messages: list[dict], output: type[T],
        max_tokens: int = 16000, effort: str = "medium", one_time: bool = False,
    ) -> T:
        if budget_state(self.conn, self.settings, self.now()) == "bloqueado":
            raise BudgetExceeded("Limite mensal de IA atingido")
        fmt = {"type": "json_schema", "schema": anthropic.transform_schema(output)}
        kw = dict(model=model, max_tokens=max_tokens, system=system, messages=messages,
                  output_config={"effort": effort, "format": fmt})
        api = self.client.messages
        if model in FALLBACK_MODELS:
            api, kw = self.client.beta.messages, {**kw, "betas": [FALLBACK_BETA], "fallbacks": "default"}
        if max_tokens > NONSTREAM_MAX_TOKENS:
            async with api.stream(**kw) as stream:
                resp = await stream.get_final_message()
        else:
            resp = await api.create(**kw)
        # a validação é feita aqui, depois de gravar o custo: resposta inválida também é paga
        self._record(model, resp.model, purpose, one_time, resp.usage)
        await self._alert()
        if resp.stop_reason == "refusal":
            raise Refused(getattr(resp.stop_details, "category", None))
        if resp.stop_reason == "max_tokens":
            raise InvalidOutput(f"resposta cortada no limite de {max_tokens} tokens")
        text = "".join(b.text for b in resp.content if b.type == "text")
        if not text:
            raise InvalidOutput("resposta sem saída estruturada")
        try:
            return output.model_validate_json(text)
        except ValidationError as e:
            raise InvalidOutput(str(e)) from e

    def fits(self, usd: float) -> bool:
        """Se uma chamada estimada em `usd` cabe no que sobra do limite do mês."""
        return month_spent(self.conn, self.now(), self.settings.tz) + usd <= self.settings.budget_usd

    def _record(self, requested: str, answered: str | None, purpose: str, one_time: bool, u: anthropic.types.Usage) -> None:
        """Grava o modelo que respondeu (o fallback do servidor pode trocar). Sem preço dele, usa o do pedido."""
        model = answered or requested
        priced = model if model in self.settings.prices else requested
        if priced != model:
            log.warning("modelo %s sem preço no config.toml: custo calculado com o preço de %s", model, requested)
        self.conn.execute(
            "INSERT INTO api_costs (ts_utc, model, purpose, one_time, input_tokens, output_tokens,"
            " cache_write_tokens, cache_read_tokens, usd) VALUES (?,?,?,?,?,?,?,?,?)",
            (self.now().astimezone(UTC).isoformat(timespec="seconds"), model, purpose, int(one_time),
             u.input_tokens, u.output_tokens, u.cache_creation_input_tokens or 0,
             u.cache_read_input_tokens or 0, cost_usd(priced, u, self.settings.prices)),
        )
        self.conn.commit()

    async def _alert(self) -> None:
        s, now = self.settings, self.now()
        spent = month_spent(self.conn, now, s.tz)
        if spent >= s.budget_usd:
            key, msg = "orcamento100", f"Limite mensal de IA atingido (US$ {spent:.2f}). A IA fica pausada até o mês virar."
        elif spent >= s.budget_usd * s.budget_alert_ratio:
            key = "orcamento80"
            msg = f"Uso de IA passou de {s.budget_alert_ratio:.0%} do limite mensal (US$ {spent:.2f} de US$ {s.budget_usd:.2f})."
        else:
            return
        cur = self.conn.execute("INSERT OR IGNORE INTO alerts_sent (day, key) VALUES (?, ?)", (month_key(now, s.tz), key))
        self.conn.commit()
        if cur.rowcount:
            try:
                await self.notify(msg)
            except Exception:
                log.warning("alerta de orçamento não enviado", exc_info=True)

    async def estimate_usd(self, *, model: str, system: list[dict], messages: list[dict], expected_output_tokens: int) -> float:
        n = await self.client.messages.count_tokens(model=model, system=system, messages=messages)
        p = self.settings.prices[model]
        usd = (n.input_tokens * p.input + expected_output_tokens * p.output) / 1_000_000
        long = p.long_prompt_tokens is not None and n.input_tokens > p.long_prompt_tokens
        return usd * (p.long_prompt_mult if long else 1.0)

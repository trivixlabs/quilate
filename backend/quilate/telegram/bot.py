"""Bot do Telegram: só envia resumo e alertas ao chat configurado. Não lê nenhuma mensagem recebida."""
from html import escape
from typing import TYPE_CHECKING

import httpx

from quilate.signals.rubric import fmt_num

if TYPE_CHECKING:
    from quilate.ai.verdict import VerdictRecord
    from quilate.cycle import CycleReport

DISCLAIMER = "Material de apoio à decisão, não é recomendação de investimento."
DASHBOARD = "http://127.0.0.1:8000"
MAX_LEN = 4000
MAX_ERROR = 500


def usd(x: float) -> str:
    return ("US$ −" if x < 0 else "US$ ") + fmt_num(abs(x), 2)


def _split(text: str) -> list[str]:
    """Divide em linhas inteiras, então nunca corta uma tag que mora numa linha.
    ponytail: linha única acima do limite é cortada seca; as nossas linhas são curtas."""
    parts, cur = [], ""
    for line in text.split("\n"):
        while len(line) > MAX_LEN:
            if cur:
                parts.append(cur)
                cur = ""
            parts.append(line[:MAX_LEN])
            line = line[MAX_LEN:]
        if cur and len(cur) + 1 + len(line) > MAX_LEN:
            parts.append(cur)
            cur = line
        else:
            cur = f"{cur}\n{line}" if cur else line
    return parts + [cur]


class Bot:
    def __init__(self, http: httpx.AsyncClient, token: str, chat_id: int):
        self._http, self._token, self._chat_id = http, token, chat_id

    async def send(self, text: str) -> None:
        for part in _split(text):
            try:
                r = await self._http.post(f"https://api.telegram.org/bot{self._token}/sendMessage",
                                          json={"chat_id": self._chat_id, "text": part, "parse_mode": "HTML",
                                                "disable_web_page_preview": True})
            except httpx.HTTPError as e:  # o texto do erro do httpx traz a URL com o token
                raise RuntimeError(f"Telegram: falha de rede ({type(e).__name__})") from None
            if r.status_code >= 400:
                raise RuntimeError(f"Telegram respondeu {r.status_code}")


def _syms(recs: "list[VerdictRecord]") -> str:
    return ", ".join(f"{escape(r.symbol)} ({escape(r.final_verdict)})" for r in recs) or "nenhum"


def format_daily(rep: "CycleReport", total_usd: float, pnl_usd: float, spent_usd: float) -> str:
    lines = [f"<b>Resumo de {rep.day.strftime('%d/%m/%Y')}</b>", f"Patrimônio: {usd(total_usd)}",
             f"Resultado: {usd(pnl_usd)}", f"Vereditos que mudaram: {_syms(rep.changed)}"]
    for v in ("Sair", "Reduzir"):
        lines.append(f"{v}: {_syms([r for r in rep.verdicts if r.final_verdict == v])}")
    lines += [f"Aviso: {escape(w)}" for w in rep.warnings]
    lines += [f"Gasto do mês com IA: {usd(spent_usd)}", DASHBOARD, DISCLAIMER]
    return "\n".join(lines)


def format_change(old: str, new: "VerdictRecord", reason: str = "") -> str:
    head = f"{escape(reason)} " if reason else ""
    return (f"{head}Veredito de <b>{escape(new.symbol)}</b>: {escape(new.final_verdict)} "
            f"(antes: {escape(old)}).\n{DISCLAIMER}")


def format_failure(exchange: str, error: str) -> str:
    return f"Falha ao sincronizar {escape(exchange.capitalize())}: {escape(error[:MAX_ERROR])}"

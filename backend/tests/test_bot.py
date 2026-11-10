import json
from dataclasses import replace
from datetime import date

import httpx
import pytest

from quilate.analyst import subject
from quilate.config import load_settings
from quilate.cycle import CycleReport
from quilate.telegram.bot import Bot, format_change, format_daily, format_failure

DISCLAIMER = "Material de apoio à decisão, não é recomendação de investimento."


def rec(symbol="ARB", final="Sair", **kw):
    from quilate.ai.verdict import VerdictRecord
    base = dict(day="2026-11-04", symbol=symbol, trigger="diario", rubric_verdict=final, ai_verdict=None,
                final_verdict=final, confidence=0.7, signals=[], pros=[], cons=[], main_risk="queda forte",
                cited_ids=[], no_analyst=False, flag=None, price_usd=1.0, price_btc=0.00001,
                created_utc="2026-11-04T12:00:00+00:00")
    return VerdictRecord(**{**base, **kw})


REP = CycleReport(date(2026, 11, 4), verdicts=[rec("ARB", "Sair"), rec("OP", "Reduzir"), rec("ETH", "Manter")],
                  changed=[rec("ARB", "Sair")], warnings=["Ana não postou até 12h"])


async def test_send_goes_only_to_configured_chat(respx_mock):
    route = respx_mock.post("https://api.telegram.org/botT/sendMessage").respond(json={"ok": True})
    await Bot(httpx.AsyncClient(), "T", 42).send("oi")
    body = json.loads(route.calls[0].request.content)
    assert body["chat_id"] == 42 and body["parse_mode"] == "HTML"


def test_daily_has_disclaimer_and_link():
    t = format_daily(REP, 12_000, -800, 7.4)
    assert DISCLAIMER in t and "http://127.0.0.1:8000" in t
    assert "US$ 12.000,00" in t and "US$ −800,00" in t and "US$ 7,40" in t
    assert "ARB" in t and "OP" in t and "Ana não postou" in t


def test_html_is_escaped():
    assert "&lt;b&gt;" in format_change("Manter", rec(symbol="<b>"))
    assert "&lt;i&gt;" in format_failure("<i>", "a<b")



def test_analyst_name_is_escaped_once():
    s = replace(load_settings(), analyst_name="Ana & Co")
    t = format_change("Sair", rec(final="Manter"), f"{subject(s)} falou de ARB.")
    t += format_daily(CycleReport(date(2026, 11, 4), warnings=[f"{subject(s)} não postou até 12h"]), 0, 0, 0)
    assert t.count("Ana &amp; Co") == 2 and "&amp;amp;" not in t

async def test_long_message_splits_on_lines_in_order(respx_mock):
    route = respx_mock.post("https://api.telegram.org/botT/sendMessage").respond(json={"ok": True})
    lines = [f"<b>linha {i}</b> " + "x" * 90 for i in range(100)]
    await Bot(httpx.AsyncClient(), "T", 42).send("\n".join(lines))
    parts = [json.loads(c.request.content)["text"] for c in route.calls]
    assert len(parts) > 1 and all(len(p) <= 4000 for p in parts)
    assert "\n".join(parts).split("\n") == lines


async def test_http_error_hides_token(respx_mock):
    respx_mock.post("https://api.telegram.org/botSEGREDO/sendMessage").respond(status_code=401)
    with pytest.raises(RuntimeError) as e:
        await Bot(httpx.AsyncClient(), "SEGREDO", 42).send("oi")
    assert "SEGREDO" not in str(e.value) and "401" in str(e.value)

import json
from dataclasses import replace
from datetime import UTC, datetime
from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from pydantic import BaseModel

from quilate.ai.claude import Claude, InvalidOutput, Refused
from quilate.budget import BudgetExceeded
from quilate.config import load_settings

NOW = datetime(2026, 6, 15, 12, tzinfo=UTC)


class VerdictOut(BaseModel):
    text: str


class _Stream:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get_final_message(self):
        return self.resp


class FakeAnthropic:
    """create/stream devolvem a resposta crua; parse imita o SDK, que valida a saída antes de devolver."""

    def __init__(self, stop_reason="end_turn", category=None, text='{"text": "ok"}', model=None):
        self.calls = 0
        self.kwargs = []
        self.beta_kwargs = []
        self.streamed = []
        self.stop_reason, self.category, self.text, self.model = stop_reason, category, text, model
        self.messages = SimpleNamespace(parse=self._parse, create=self._create, stream=self._stream, count_tokens=self._count)
        self.beta = SimpleNamespace(messages=SimpleNamespace(parse=self._beta_parse, create=self._beta_create,
                                                             stream=self._beta_stream))

    async def _create(self, **kw):
        self.kwargs.append(kw)
        return self._resp(kw)

    async def _beta_create(self, **kw):
        self.beta_kwargs.append(kw)
        return self._resp(kw)

    def _stream(self, **kw):
        self.kwargs.append(kw)
        self.streamed.append(kw)
        return _Stream(self._resp(kw))

    def _beta_stream(self, **kw):
        self.beta_kwargs.append(kw)
        self.streamed.append(kw)
        return _Stream(self._resp(kw))

    async def _parse(self, **kw):
        return self._parsed(await self._create(**kw), kw)

    async def _beta_parse(self, **kw):
        return self._parsed(await self._beta_create(**kw), kw)

    def _parsed(self, resp, kw):
        resp.parsed_output = kw["output_format"].model_validate_json(self.text) if self.text else None
        return resp

    async def _count(self, **kw):
        return SimpleNamespace(input_tokens=1_000_000)

    def _resp(self, kw):
        self.calls += 1
        return SimpleNamespace(
            model=self.model or kw["model"],
            stop_reason=self.stop_reason,
            stop_details=SimpleNamespace(category=self.category) if self.category else None,
            usage=SimpleNamespace(input_tokens=1000, output_tokens=500, cache_creation_input_tokens=None, cache_read_input_tokens=0),
            content=[SimpleNamespace(type="text", text=self.text)] if self.text else [],
        )


@pytest.fixture
def settings():
    return replace(load_settings(), budget_usd=50, budget_alert_ratio=0.8)  # sem depender do arquivo local


@pytest.fixture
def sent():
    return []


@pytest.fixture
def notify(sent):
    async def _n(text):
        sent.append(text)
    return _n


def add_cost(db, usd):
    db.execute("INSERT INTO api_costs (ts_utc, model, purpose, usd) VALUES ('2026-06-10T12:00:00+00:00','m','t',?)", (usd,))


def make(api, db, settings, notify):
    return Claude(api, db, settings, notify, now=lambda: NOW)


async def call(c, model="claude-sonnet-5-5", **kw):
    return await c.parse(purpose="veredito", model=model, system=[], messages=[], output=VerdictOut, **kw)


async def test_blocked_budget_makes_no_call(db, settings, notify):
    add_cost(db, 50)
    api = FakeAnthropic()
    with pytest.raises(BudgetExceeded):
        await call(make(api, db, settings, notify))
    assert api.calls == 0


async def test_success_records_cost_and_returns_parsed(db, settings, notify):
    api = FakeAnthropic()
    out = await call(make(api, db, settings, notify))
    assert out.text == "ok"
    row = db.execute("SELECT usd, input_tokens, cache_write_tokens, one_time FROM api_costs").fetchone()
    assert row["usd"] == pytest.approx(0.007) and row["input_tokens"] == 1000 and row["cache_write_tokens"] == 0 and row["one_time"] == 0
    kw = api.beta_kwargs[0]
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["fallbacks"] == "default"
    assert kw["output_config"] == {"effort": "medium",
                                   "format": {"type": "json_schema", "schema": anthropic.transform_schema(VerdictOut)}}
    assert not {"thinking", "temperature", "top_p", "top_k"} & kw.keys()


async def test_haiku_has_no_fallback(db, settings, notify):
    api = FakeAnthropic()
    await call(make(api, db, settings, notify), model="claude-haiku-5-5")
    assert api.beta_kwargs == [] and "fallbacks" not in api.kwargs[0]


async def test_refusal_raises_and_cost_is_recorded(db, settings, notify):
    api = FakeAnthropic(stop_reason="refusal", category="general_harms", text=None)
    with pytest.raises(Refused) as e:
        await call(make(api, db, settings, notify))
    assert e.value.category == "general_harms"
    assert db.execute("SELECT count(*) FROM api_costs").fetchone()[0] == 1


async def test_none_parsed_output_is_invalid(db, settings, notify):
    with pytest.raises(InvalidOutput):
        await call(make(FakeAnthropic(text=None), db, settings, notify))


async def test_alert_sent_once_at_80_percent(db, settings, notify, sent):
    add_cost(db, 40)
    c = make(FakeAnthropic(), db, settings, notify)
    await call(c)
    await call(c)
    assert len(sent) == 1 and "80%" in sent[0]
    assert db.execute("SELECT day, key FROM alerts_sent").fetchall()[0]["key"] == "orcamento80"


async def test_alert_at_100_percent_and_notify_failure_is_swallowed(db, settings):
    add_cost(db, 49.995)

    async def boom(text):
        raise RuntimeError("telegram fora")

    out = await call(make(FakeAnthropic(), db, settings, boom))
    assert out.text == "ok"
    assert db.execute("SELECT key FROM alerts_sent").fetchone()["key"] == "orcamento100"


async def test_estimate_usd(db, settings, notify):
    c = make(FakeAnthropic(), db, settings, notify)
    got = await c.estimate_usd(model="claude-sonnet-5-5", system=[], messages=[], expected_output_tokens=100_000)
    assert got == pytest.approx(2.0 + 1.0)


async def test_invalid_output_still_records_cost(db, settings, notify):
    with pytest.raises(InvalidOutput):
        await call(make(FakeAnthropic(text='{"texto": "campo errado"}'), db, settings, notify))
    assert db.execute("SELECT usd FROM api_costs").fetchone()["usd"] == pytest.approx(0.007)


async def test_cut_at_max_tokens_is_invalid_and_paid(db, settings, notify):
    with pytest.raises(InvalidOutput, match="limite"):
        await call(make(FakeAnthropic(stop_reason="max_tokens", text='{"text": "o'), db, settings, notify))
    assert db.execute("SELECT count(*) FROM api_costs").fetchone()[0] == 1


async def test_large_max_tokens_streams(db, settings, notify):
    api = FakeAnthropic()
    out = await call(make(api, db, settings, notify), model="claude-opus-5-5", max_tokens=64_000)
    assert out.text == "ok" and api.streamed and api.streamed[0]["max_tokens"] == 64_000
    assert api.streamed[0]["fallbacks"] == "default"


async def test_records_the_model_that_answered(db, settings, notify, caplog):
    await call(make(FakeAnthropic(model="claude-opus-5-5"), db, settings, notify))  # fallback do servidor
    await call(make(FakeAnthropic(model="claude-novo-9"), db, settings, notify))
    rows = db.execute("SELECT model, usd FROM api_costs ORDER BY id").fetchall()
    assert (rows[0]["model"], rows[0]["usd"]) == ("claude-opus-5-5", pytest.approx(0.014))  # preço do Opus
    assert (rows[1]["model"], rows[1]["usd"]) == ("claude-novo-9", pytest.approx(0.007))  # sem preço: o do pedido
    assert any("claude-novo-9" in r.message for r in caplog.records)


def _sse(events: list[dict]) -> str:
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


@pytest.mark.parametrize("model,max_tokens", [("claude-haiku-5-5", 1000), ("claude-sonnet-5-5", 1000),
                                              ("claude-opus-5-5", 64_000)])
async def test_real_sdk_accepts_the_request(db, settings, notify, model, max_tokens):
    """O SDK de verdade monta o pedido (create, beta com fallbacks, streaming). Sem rede: MockTransport responde."""
    msg = {"id": "m", "type": "message", "role": "assistant", "model": model, "stop_reason": "end_turn",
           "stop_sequence": None, "content": [{"type": "text", "text": '{"text": "ok"}'}],
           "usage": {"input_tokens": 10, "output_tokens": 5}}
    start = {**msg, "content": [], "stop_reason": None, "usage": {"input_tokens": 10, "output_tokens": 1}}
    sse = _sse([{"type": "message_start", "message": start},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": '{"text": "ok"}'}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                 "usage": {"output_tokens": 5}},
                {"type": "message_stop"}])
    sent = []

    def handler(request):
        sent.append(json.loads(request.content))
        if sent[-1].get("stream"):
            return httpx2.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        return httpx2.Response(200, json=msg)

    api = anthropic.AsyncAnthropic(api_key="teste", http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handler)))
    out = await call(make(api, db, settings, notify), model=model, max_tokens=max_tokens)
    assert out.text == "ok" and sent[0]["output_config"]["format"]["type"] == "json_schema"
    assert ("fallbacks" in sent[0]) == (model != "claude-haiku-5-5")
    assert bool(sent[0].get("stream")) == (max_tokens > 16_000)
    assert db.execute("SELECT output_tokens FROM api_costs").fetchone()[0] == 5

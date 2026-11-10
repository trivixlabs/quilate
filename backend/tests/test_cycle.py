import asyncio
import json
import logging
import sqlite3
import threading
import time
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from quilate import cycle
from quilate.ai.verdict import BatchOut, VerdictOut
from quilate.config import load_settings
from quilate.context import AppContext
from quilate.cycle import (
    alert_once,
    check_delisting,
    check_intraday,
    daily_due,
    in_thread,
    on_analyst_message,
    refresh_knowledge,
    run_daily,
    run_daily_if_due,
    sync_and_alert,
)
from quilate.db import connect, migrate
from quilate.exchanges.client import UnsafeKeyError
from quilate.exchanges.live import PriceBook, Tick
from quilate.knowledge.mentions import StanceOut
from quilate.scheduler import _job, start_scheduler
from quilate.telegram.collector import MessageRow

DAY = date(2026, 11, 4)
TZ = ZoneInfo("America/Sao_Paulo")


def local(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=TZ)


NOW = local("2026-11-04 15:00")


def tick(symbol, price):
    return Tick("binance", symbol, price, 1)


def seed_msg(db, msg_id, text, analyst, topic, at):
    db.execute("INSERT INTO messages (msg_id, topic_id, is_analyst, date_utc, text) VALUES (?,?,?,?,?)",
               (msg_id, topic, int(analyst), at.astimezone(UTC).isoformat(), text))
    db.commit()


def seed_verdict(db, day, symbol="ARB", final="Manter", trigger="diario"):
    db.execute("INSERT INTO verdicts (day, symbol, trigger, rubric_verdict, final_verdict, signals_json, pros_json,"
               " cons_json, main_risk, cited_json, price_usd, price_btc, created_utc)"
               " VALUES (?,?,?,?,?,'[]','[]','[]','','[]',1,1,'2026-11-01T00:00:00+00:00')",
               (day, symbol, trigger, final, final))
    db.commit()


def seed_daily_verdict(db, day):
    seed_verdict(db, day)


def seed_coin(db, symbol, close, qty, days=40):
    for i in range(days):
        d = (DAY - timedelta(days=days - 1 - i)).isoformat()
        db.execute("INSERT INTO candles VALUES ('binance',?,'USDT',?,?,?,?,?,1e9)", (symbol, d, close, close, close, close))
    if qty:
        db.execute("INSERT INTO positions VALUES ('binance',?,'spot',?,'2026-11-04T00:00:00+00:00',0)", (symbol, qty))
    db.commit()


class FakeClaude:
    def __init__(self, verdict="Manter"):
        self.verdict, self.calls = verdict, []

    async def parse(self, **kw):
        self.calls.append(kw["output"])
        if kw["output"] is VerdictOut:
            return VerdictOut(verdict=self.verdict, confidence=0.7, pros=[], cons=[], main_risk="",
                              cited_ids=[], no_analyst=False)
        if kw["output"] is BatchOut:
            return BatchOut(verdicts=[])
        return kw["output"](items=[])  # menções: nada extraído


class FakeEmbedder:
    def encode(self, texts):
        return [[0.0] * 767 + [1.0] for _ in texts]


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send(self, text):
        self.sent.append(text)

    @property
    def sent_count(self):
        return len(self.sent)


class FailingClient:
    async def check_read_only(self):
        raise RuntimeError("tempo esgotado")


@pytest.fixture
def settings(tmp_path):
    return replace(load_settings(), data_dir=tmp_path, analyst_name="Ana", trigger_topic=101, group_topics={101: "MARKET UPDATES", 102: "GENERAL"}, analyst_username="usuario_do_analista")


@pytest.fixture
def db(settings):  # no mesmo arquivo de settings.db_path: as threads abrem a própria conexão nele
    conn = connect(settings.db_path)
    migrate(conn)
    yield conn
    conn.close()


@pytest.fixture
def ctx(db, settings):
    seed_coin(db, "BTC", 80_000.0, 0)
    seed_coin(db, "ARB", 0.41, 1000)  # US$ 410
    seed_coin(db, "POEIRA", 1.0, 9)  # US$ 9: poeira
    return AppContext(settings=settings, conn=db, clients={}, book=PriceBook(), claude=FakeClaude(),
                      embedder=FakeEmbedder(), http=None, bot=FakeBot(), hub=None)


def test_due_after_analyst_post(db, settings):
    seed_msg(db, 1, "análise", analyst=True, topic=101, at=local("2026-11-04 08:42"))
    assert daily_due(db, local("2026-11-04 08:45"), settings) is True


def test_due_ignores_other_topics_and_yesterday(db, settings):
    seed_msg(db, 1, "análise", analyst=True, topic=1, at=local("2026-11-04 08:42"))
    seed_msg(db, 2, "análise", analyst=True, topic=101, at=local("2026-11-03 23:50"))
    seed_msg(db, 3, "análise", analyst=False, topic=101, at=local("2026-11-04 08:43"))
    assert daily_due(db, local("2026-11-04 08:45"), settings) is False


def test_due_at_cutoff_without_post(db, settings):
    assert daily_due(db, local("2026-11-04 11:59"), settings) is False
    assert daily_due(db, local("2026-11-04 12:00"), settings) is True


def test_not_due_twice(db, settings):
    seed_daily_verdict(db, "2026-11-04")
    assert daily_due(db, local("2026-11-04 15:00"), settings) is False


async def test_run_daily_skips_dust_and_warns_without_analyst(ctx):
    ctx.conn.execute("INSERT INTO positions VALUES ('binance','SEMPRECO','spot',50,'2026-11-04T00:00:00+00:00',0)")
    ctx.conn.commit()
    rep = await run_daily(ctx, DAY)
    assert [r.symbol for r in rep.verdicts] == ["ARB"]  # POEIRA (US$ 9) fora
    assert rep.verdicts[0].trigger == "diario" and rep.verdicts[0].ai_verdict == "Manter"
    assert "Ana não postou até 12h" in rep.warnings
    assert any("SEMPRECO" in w for w in rep.warnings)  # sem preço: aviso, o ciclo continua
    assert ctx.bot.sent_count == 1
    assert "Material de apoio à decisão, não é recomendação de investimento." in ctx.bot.sent[0]
    assert daily_due(ctx.conn, NOW, ctx.settings) is False


async def test_run_daily_without_trigger_topic_does_not_wait_for_a_post(ctx):
    ctx.settings = replace(ctx.settings, trigger_topic=0)
    rep = await run_daily(ctx, DAY)
    assert not any("não postou" in w for w in rep.warnings)


async def test_daily_summary_warns_once_about_unverified_permissions(ctx):
    class Quiet:  # corretora sem posição: só a chave importa aqui
        async def check_read_only(self): pass
        async def fetch_holdings(self): return []
        async def fetch_trades(self, sym, since): return []

    ctx.clients = {"mexc": Quiet(), "gate": Quiet()}
    rep = await run_daily(ctx, DAY)
    assert [w for w in rep.warnings if "permissões" in w] == [
        "gate: permissões da chave confirmadas por você no site, não pela API",
        "mexc: permissões da chave confirmadas por você no site, não pela API"]
    assert "gate: permissões da chave confirmadas" in ctx.bot.sent[0]
    rep = await run_daily(ctx, DAY + timedelta(days=1))
    assert not [w for w in rep.warnings if "permissões" in w]  # uma vez só


async def test_run_daily_reports_changed_verdict(ctx):
    seed_msg(ctx.conn, 1, "análise do dia", analyst=True, topic=101, at=local("2026-11-04 08:42"))
    seed_verdict(ctx.conn, "2026-11-03", "ARB", "Sair")
    rep = await run_daily(ctx, DAY)
    assert [r.symbol for r in rep.changed] == ["ARB"]
    assert not any("não postou" in w for w in rep.warnings)
    assert "ARB" in ctx.bot.sent[0]


async def test_empty_portfolio_runs_once(ctx):
    ctx.conn.execute("DELETE FROM positions")
    ctx.conn.commit()
    await run_daily(ctx, DAY)
    assert daily_due(ctx.conn, NOW, ctx.settings) is False


async def test_many_coins_send_small_ones_in_batch(ctx):
    ctx.conn.execute("UPDATE positions SET qty=1000000 WHERE symbol='ARB'")  # US$ 410 mil
    for i in range(50):
        seed_coin(ctx.conn, f"C{i:02}", 1.0, 11)  # US$ 11 cada: acima da poeira, abaixo de 1%
    rep = await run_daily(ctx, DAY)
    assert len(rep.verdicts) == 51
    assert ctx.claude.calls.count(VerdictOut) == 1 and BatchOut in ctx.claude.calls


def analyst_row(msg_id, text, topic=1, analyst=1):
    return MessageRow(msg_id, topic, 7, "usuario_do_analista", analyst, NOW.astimezone(UTC).isoformat(), text,
                      None, None, None)


async def test_analyst_mention_recalcs_with_ai(ctx):
    seed_verdict(ctx.conn, "2026-11-03", "ARB", "Sair")
    row = analyst_row(50, "ARB e SOL hoje, POEIRA também")
    seed_msg(ctx.conn, 50, row.text, analyst=True, topic=1, at=NOW)
    await on_analyst_message(ctx, row)
    rows = ctx.conn.execute("SELECT symbol, ai_verdict FROM verdicts WHERE trigger='analista'").fetchall()
    assert [tuple(r) for r in rows] == [("ARB", "Manter")]  # SOL fora da carteira, POEIRA é poeira
    assert ctx.bot.sent_count == 1 and "ARB" in ctx.bot.sent[0]  # mudou de Sair para Manter
    await on_analyst_message(ctx, row)  # a mesma mensagem editada não recalcula de novo
    await on_analyst_message(ctx, analyst_row(51, "ARB", analyst=0))  # membro do grupo não é gatilho
    assert ctx.conn.execute("SELECT COUNT(*) FROM verdicts WHERE trigger='analista'").fetchone()[0] == 1


async def test_daily_post_waits_for_the_cycle(ctx):
    await on_analyst_message(ctx, analyst_row(52, "ARB", topic=101))
    assert ctx.conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 0


def test_trigger_topic_zero_never_counts_as_the_daily_post(db, settings):
    s = replace(settings, trigger_topic=0)
    seed_msg(db, 1, "análise", True, None, local("2026-11-04 08:42"))
    seed_msg(db, 2, "análise", True, 0, local("2026-11-04 08:43"))
    assert cycle._analyst_posted(db, DAY, s) is False
    assert not daily_due(db, local("2026-11-04 09:00"), s)


async def test_message_without_topic_recalculates_when_trigger_is_zero(ctx):
    ctx.settings = replace(ctx.settings, trigger_topic=0)
    for msg_id, topic in ((53, None), (54, 0)):
        seed_msg(ctx.conn, msg_id, "ARB", True, topic, NOW)
        await cycle.on_analyst_message(ctx, analyst_row(msg_id, "ARB", topic=topic))
    assert ctx.conn.execute("SELECT COUNT(*) FROM verdicts WHERE trigger='analista'").fetchone()[0] == 2


def movement_rows(db):
    return [tuple(r) for r in db.execute("SELECT trigger, ai_verdict, final_verdict FROM verdicts WHERE trigger='movimento'")]


async def test_move_over_10_percent_alerts_once(ctx):
    seed_verdict(ctx.conn, "2026-11-03", "ARB", "Sair")  # a régua dá Manter: o veredito muda
    ctx.book.update(tick("ARB", 0.41 * 0.95))
    await check_intraday(ctx, NOW)
    assert ctx.bot.sent_count == 0 and movement_rows(ctx.conn) == []
    ctx.book.update(tick("ARB", 0.41 * 0.89))
    await check_intraday(ctx, NOW); await check_intraday(ctx, NOW)
    assert ctx.bot.sent_count == 1 and "caiu 11%" in ctx.bot.sent[0] and "antes: Sair" in ctx.bot.sent[0]
    assert movement_rows(ctx.conn) == [("movimento", None, "Manter")]  # só a régua, uma vez no dia


async def test_move_without_verdict_change_records_but_does_not_alert(ctx):
    seed_verdict(ctx.conn, "2026-11-03", "ARB", "Manter")
    ctx.book.update(tick("ARB", 0.41 * 1.15))
    await check_intraday(ctx, NOW)
    assert ctx.bot.sent_count == 0
    assert movement_rows(ctx.conn) == [("movimento", None, "Manter")]


async def test_new_monitoring_tag_recalcs_rubric_once(ctx):
    seed_verdict(ctx.conn, "2026-11-03", "ARB", "Sair")
    for d, tag in [("2026-11-03", False), ("2026-11-04", True)]:
        ctx.conn.execute("INSERT INTO snapshots VALUES (?, 'delisting', ?)",
                         (d, json.dumps({"ARB": {"monitoring_tag": tag, "listed_on": 3}})))
    await check_delisting(ctx, DAY); await check_delisting(ctx, DAY)
    assert ctx.bot.sent_count == 1 and "Monitoring Tag" in ctx.bot.sent[0]
    rec = ctx.conn.execute("SELECT trigger, ai_verdict FROM verdicts WHERE trigger='tag'").fetchall()
    assert [tuple(r) for r in rec] == [("tag", None)]


async def test_exchange_failure_alerts_once_per_day(ctx):
    ctx.clients = {"bybit": FailingClient()}
    await sync_and_alert(ctx, NOW); await sync_and_alert(ctx, NOW)
    assert ctx.bot.sent_count == 1 and "Bybit" in ctx.bot.sent[0]


class FakeHub:
    def __init__(self):
        self.events = []

    async def broadcast(self, event):
        self.events.append(event)


async def test_cycle_and_verdict_events_reach_the_hub(ctx):
    ctx.hub = FakeHub()
    await run_daily(ctx, DAY)
    assert ctx.hub.events == [{"type": "cycle", "day": "2026-11-04"}]
    ctx.hub.events.clear()
    ctx.book.update(tick("ARB", 0.41 * 0.89))
    await check_intraday(ctx, NOW)
    assert ctx.hub.events == [{"type": "verdict", "symbol": "ARB"}]


def test_alert_once(db):
    assert alert_once(db, DAY, "falha:bybit") is True and alert_once(db, DAY, "falha:bybit") is False


async def test_scheduler_wires_every_job(ctx, memory_keyring):  # a coleta inicial não lê o Keychain real
    sched = start_scheduler(ctx)
    try:
        jobs = {j.id: j for j in sched.get_jobs()}
        assert set(jobs) == {"sync_all", "ciclo_diario", "intradiario", "coleta_diaria", "coleta_inicial",
                             "midia", "conhecimento", "manual_semanal"}
        assert str(jobs["coleta_diaria"].trigger.timezone) == "America/Sao_Paulo"
        assert jobs["sync_all"].coalesce is True and jobs["sync_all"].misfire_grace_time == 3600
    finally:
        sched.shutdown(wait=False)


async def test_history_job_skips_while_telegram_is_down(ctx, memory_keyring, monkeypatch):
    from types import SimpleNamespace

    from quilate import scheduler
    from quilate.scheduler import GROUP_START, TelegramSource
    calls, state = [], {"up": False}

    async def backfill(*a, **kw):
        calls.append(kw)
        return 0

    monkeypatch.setattr(scheduler, "backfill", backfill)
    tg = SimpleNamespace(is_connected=lambda: state["up"])
    sched = start_scheduler(ctx, telegram=TelegramSource(tg, 1, 7, GROUP_START))
    try:
        job = sched.get_job("historico")
        await job.func()
        assert calls == []  # desconectado: a rodada pula
        state["up"] = True
        await job.func()
        assert calls == [{"max_messages": 2000}]
    finally:
        sched.shutdown(wait=False)


async def test_failing_job_is_logged_not_raised(caplog):
    def boom():
        raise RuntimeError("quebrou")
    with caplog.at_level(logging.ERROR):
        await _job("teste", boom)()
    assert "teste" in caplog.text and "quebrou" in caplog.text


async def test_heavy_work_runs_in_thread_with_own_connection(ctx):
    opened, seen = [], {}

    def fake_connect(path):
        opened.append(connect(path))
        return opened[-1]

    def work(conn, n):
        seen.update(conn=conn, thread=threading.current_thread(), n=n)
        return conn.execute("SELECT COUNT(*) FROM positions").fetchone()[0]

    assert await in_thread(ctx.settings, work, 3, connect=fake_connect) == 2  # mesmo banco: ARB e POEIRA
    assert seen["conn"] is opened[0] and seen["conn"] is not ctx.conn and seen["n"] == 3
    assert seen["thread"] is not threading.main_thread()
    with pytest.raises(sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")  # fechada no fim


async def test_media_job_runs_off_loop_with_own_connection(ctx, monkeypatch, memory_keyring):
    seen = {}
    today = datetime.now(UTC).astimezone(TZ).date().isoformat()
    ctx.conn.execute("INSERT INTO snapshots VALUES (?, 'fng', '50')", (today,))  # sem coleta inicial
    ctx.conn.commit()

    def fake_process_jobs(conn, limit, out_dir=None):
        seen.update(conn=conn, limit=limit, thread=threading.current_thread(), out_dir=out_dir)
        return 0

    monkeypatch.setattr("quilate.scheduler.process_jobs", fake_process_jobs)
    sched = start_scheduler(ctx)
    try:
        await sched.get_job("midia").func()
    finally:
        sched.shutdown(wait=False)
    assert seen["limit"] == 3 and seen["conn"] is not ctx.conn and seen["thread"] is not threading.main_thread()
    assert seen["out_dir"] == ctx.settings.media_dir / "youtube"  # a pasta de dados do config, não um caminho fixo


async def test_two_analyst_messages_each_flipping_alert_twice(ctx):
    seed_verdict(ctx.conn, "2026-11-03", "ARB", "Sair")
    for msg_id, verdict in [(60, "Manter"), (61, "Sair")]:
        ctx.claude.verdict = verdict
        seed_msg(ctx.conn, msg_id, "ARB", analyst=True, topic=1, at=NOW)
        await on_analyst_message(ctx, analyst_row(msg_id, "ARB"))
    assert ctx.bot.sent_count == 2
    assert "antes: Sair" in ctx.bot.sent[0] and "antes: Manter" in ctx.bot.sent[1]


async def test_index_failure_still_extracts_mentions(ctx, monkeypatch):
    def broken(conn, embedder):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr("quilate.cycle.index_pending", broken)
    seed_msg(ctx.conn, 70, "ARB", analyst=True, topic=1, at=NOW)
    await refresh_knowledge(ctx, NOW - timedelta(hours=1))
    assert StanceOut in ctx.claude.calls


async def test_index_runs_one_at_a_time(ctx, monkeypatch):
    state = {"active": 0, "max": 0, "calls": 0}
    guard = threading.Lock()

    def fake_index(conn, embedder):
        with guard:
            state["active"] += 1
            state["calls"] += 1
            state["max"] = max(state["max"], state["active"])
        time.sleep(0.05)  # janela para a segunda chamada entrar, se não houver trava
        with guard:
            state["active"] -= 1
        return 0

    monkeypatch.setattr("quilate.cycle.index_pending", fake_index)
    await asyncio.gather(refresh_knowledge(ctx, NOW), refresh_knowledge(ctx, NOW))
    assert state["calls"] == 2 and state["max"] == 1


async def test_delisting_ignores_coin_missing_from_today(ctx):
    ctx.conn.execute("INSERT INTO snapshots VALUES ('2026-11-03', 'delisting', ?)",
                     (json.dumps({"ARB": {"monitoring_tag": False, "listed_on": 3}}),))
    ctx.conn.execute("INSERT INTO snapshots VALUES ('2026-11-04', 'delisting', ?)",
                     (json.dumps({"LINK": {"monitoring_tag": False, "listed_on": 3}}),))
    await check_delisting(ctx, DAY)
    assert ctx.bot.sent_count == 0 and ctx.conn.execute("SELECT COUNT(*) FROM verdicts").fetchone()[0] == 0


async def test_delisting_exchange_drop_alerts_with_counts(ctx):
    seed_verdict(ctx.conn, "2026-11-03", "ARB", "Sair")
    for d, n in [("2026-11-03", 3), ("2026-11-04", 2)]:
        ctx.conn.execute("INSERT INTO snapshots VALUES (?, 'delisting', ?)",
                         (d, json.dumps({"ARB": {"monitoring_tag": False, "listed_on": n}})))
    await check_delisting(ctx, DAY)
    assert ctx.bot.sent_count == 1 and "agora em 2, antes em 3" in ctx.bot.sent[0]


async def test_failed_move_recalc_retries_on_next_check(ctx, monkeypatch):
    from quilate import cycle
    real, calls = cycle.decide, []

    async def flaky(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError("sem preço para BTC")
        return await real(*a, **kw)

    monkeypatch.setattr("quilate.cycle.decide", flaky)
    ctx.book.update(tick("ARB", 0.41 * 0.89))
    await check_intraday(ctx, NOW)
    assert movement_rows(ctx.conn) == []
    await check_intraday(ctx, NOW); await check_intraday(ctx, NOW)
    assert len(calls) == 2 and len(movement_rows(ctx.conn)) == 1


class UnsafeClient:
    async def check_read_only(self):
        raise UnsafeKeyError("bybit: a chave permite trade ou saque")


async def test_unsafe_key_alerts_once_and_keeps_refusing(ctx):
    ctx.clients = {"bybit": UnsafeClient()}
    for _ in range(2):
        with pytest.raises(UnsafeKeyError):
            await sync_and_alert(ctx, NOW)
    assert ctx.bot.sent_count == 1 and "bybit" in ctx.bot.sent[0]


async def test_overlapping_refresh_extracts_each_mention_once(ctx):
    class SlowClaude(FakeClaude):
        async def parse(self, **kw):
            await asyncio.sleep(0.01)  # a outra chamada roda enquanto esta espera a IA
            return await super().parse(**kw)

    ctx.claude = SlowClaude()
    seed_msg(ctx.conn, 1, "ARB perto do alvo", analyst=True, topic=1, at=local("2026-11-04 08:00"))
    since = datetime(2026, 11, 1, tzinfo=UTC)
    await asyncio.gather(refresh_knowledge(ctx, since), refresh_knowledge(ctx, since))
    assert ctx.claude.calls == [StanceOut]
    assert ctx.conn.execute("SELECT COUNT(*) FROM mentions WHERE symbol='ARB'").fetchone()[0] == 1


async def test_daily_cycle_collects_first_when_today_has_no_snapshot(ctx, monkeypatch):
    collected = []

    async def fake_collect(ctx, day):
        collected.append(day)

    monkeypatch.setattr(cycle, "collect_and_check", fake_collect)
    assert await run_daily_if_due(ctx, NOW) is not None  # 15h, depois do horário limite
    assert collected == [DAY]


async def test_daily_cycle_skips_collect_when_snapshot_exists(ctx, monkeypatch):
    collected = []

    async def fake_collect(ctx, day):
        collected.append(day)

    monkeypatch.setattr(cycle, "collect_and_check", fake_collect)
    ctx.conn.execute("INSERT INTO snapshots VALUES (?, 'fng', '{}')", (DAY.isoformat(),))
    ctx.conn.commit()
    assert await run_daily_if_due(ctx, NOW) is not None
    assert collected == []


async def test_concurrent_syncs_run_one_at_a_time(ctx):
    state = {"active": 0, "peak": 0}

    class SlowClient:
        async def check_read_only(self): pass

        async def fetch_holdings(self):
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            await asyncio.sleep(0.01)  # a outra sincronização tentaria entrar aqui
            state["active"] -= 1
            return []

        async def fetch_trades(self, sym, since): return []

    ctx.clients = {"binance": SlowClient()}
    await asyncio.gather(sync_and_alert(ctx, NOW), sync_and_alert(ctx, NOW))
    assert state["peak"] == 1

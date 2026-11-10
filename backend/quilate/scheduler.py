"""Agendador: só liga cada job à sua função. A lógica fica em cycle.py e nos módulos de cada parte."""
import inspect
import logging
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any, NamedTuple
from zoneinfo import ZoneInfo

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from quilate.ai.playbook import propose_update
from quilate.cycle import (
    check_intraday,
    collect_and_check,
    in_thread,
    local_day,
    refresh_knowledge,
    run_daily_if_due,
    sync_and_alert,
)
from quilate.media.worker import process_jobs
from quilate.telegram.collector import backfill

log = logging.getLogger(__name__)

# Piso do histórico. Não usamos Channel.date: para quem é membro, o Telegram devolve ali a data de entrada,
# não a de criação, e o histórico anterior se perderia. O backfill para sozinho na mensagem mais antiga.
GROUP_START = datetime(2015, 1, 1, tzinfo=UTC)
BACKFILL_BATCH = 2000
KNOWLEDGE_DAYS = 365
PLAYBOOK_DAYS = 7


class TelegramSource(NamedTuple):
    client: Any
    group_id: int
    analyst_id: int
    since_utc: datetime = GROUP_START


def _job(name: str, fn):
    """Envolve o job como coroutine (no APScheduler 3, função comum iria para uma thread com ctx.conn) e só
    registra o erro. Trabalho pesado vai para thread por in_thread, com conexão própria."""
    async def run() -> None:
        try:
            r = fn()
            if inspect.isawaitable(r):
                await r
        except Exception:
            log.exception("job %s falhou", name)
    return run


def start_scheduler(ctx, telegram: TelegramSource | None = None) -> AsyncIOScheduler:
    s, conn = ctx.settings, ctx.conn
    tz = ZoneInfo(s.tz)
    sched = AsyncIOScheduler(timezone=tz, job_defaults={"coalesce": True, "misfire_grace_time": 3600})

    def now() -> datetime:
        return datetime.now(UTC)

    def add(name: str, fn, trigger: str, **kw) -> None:
        sched.add_job(_job(name, fn), trigger, id=name, **kw)

    add("sync_all", lambda: sync_and_alert(ctx, now()), "interval", minutes=s.sync_minutes)
    add("ciclo_diario", lambda: run_daily_if_due(ctx, now()), "interval", minutes=2)
    add("intradiario", lambda: check_intraday(ctx, now()), "interval", minutes=s.sync_minutes)
    add("coleta_diaria", lambda: collect_and_check(ctx, local_day(now(), s.tz)), "cron", hour=3, minute=0)
    if not conn.execute("SELECT 1 FROM snapshots WHERE day=?", (local_day(now(), s.tz).isoformat(),)).fetchone():
        add("coleta_inicial", lambda: collect_and_check(ctx, local_day(now(), s.tz)), "date", run_date=datetime.now(tz))
    add("midia", lambda: in_thread(s, partial(process_jobs, out_dir=s.media_dir / "youtube"), 3), "interval", minutes=10)
    add("conhecimento", lambda: refresh_knowledge(ctx, now() - timedelta(days=KNOWLEDGE_DAYS)), "interval", minutes=30)
    add("manual_semanal", lambda: propose_update(ctx.claude, conn, now() - timedelta(days=PLAYBOOK_DAYS), ctx.settings),
        "cron", day_of_week="sun", hour=20, minute=0)
    sched.start()
    if telegram:
        schedule_history(sched, ctx, telegram)
    return sched


def schedule_history(sched, ctx, telegram: TelegramSource) -> None:
    """Job de cada hora que continua o histórico do grupo. Com o Telegram fora do ar, a rodada só pula."""
    s = ctx.settings

    def run():
        if not telegram.client.is_connected():
            log.info("historico: Telegram desconectado, rodada pulada")
            return None
        return backfill(telegram.client, ctx.conn, telegram.group_id, telegram.since_utc, s.media_dir,
                        telegram.analyst_id, lambda n: None, max_messages=BACKFILL_BATCH)

    sched.add_job(_job("historico", run), "interval", hours=1, id="historico")

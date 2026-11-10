"""Ciclo diário e gatilhos fora do horário: sincroniza, recalcula vereditos e avisa pelo bot."""
import asyncio
import html
import logging
import math
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from quilate.ai.verdict import VerdictRecord, decide, decide_many, last_price
from quilate.analyst import subject
from quilate.budget import month_spent
from quilate.db import connect
from quilate.exchanges.client import UNVERIFIED, UnsafeKeyError
from quilate.exchanges.cost_basis import Trade, compute_cost_basis, unrealized_pnl
from quilate.exchanges.sync import SyncReport, sync_all
from quilate.knowledge.index import index_pending
from quilate.knowledge.mentions import find_symbols, run_mentions
from quilate.market.collect import STABLES, collect_daily
from quilate.signals.inputs import daily_closes, snapshot
from quilate.signals.rubric import fmt_num
from quilate.telegram.bot import format_change, format_daily, format_failure
from quilate.telegram.bot import usd as _usd
from quilate.telegram.collector import MessageRow

log = logging.getLogger(__name__)

BATCH_ABOVE = 50  # acima disso, as moedas com menos de 1% da carteira vão numa chamada só
SMALL_SHARE = 0.01
TOP_NAMES = 100
DONE_KEY = "ciclo"
# ponytail: trava de thread, não asyncio.Lock: index_pending roda em thread e a trava não fica presa a um loop
_INDEX_LOCK = threading.Lock()


@dataclass
class CycleReport:
    day: date
    verdicts: list[VerdictRecord] = field(default_factory=list)
    changed: list[VerdictRecord] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def local_day(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date()


def _utc_bounds(day: date, tz: str) -> tuple[str, str]:
    start = datetime.combine(day, time(), ZoneInfo(tz))
    return tuple(d.astimezone(UTC).isoformat() for d in (start, start + timedelta(days=1)))


def alert_once(conn, day: date, key: str) -> bool:
    """Verdadeiro só na primeira vez que a chave aparece no dia."""
    cur = conn.execute("INSERT OR IGNORE INTO alerts_sent (day, key) VALUES (?, ?)", (day.isoformat(), key))
    conn.commit()
    return cur.rowcount == 1


async def _send(ctx, text: str) -> None:
    try:
        await ctx.bot.send(text)
    except Exception:
        log.exception("mensagem do bot não enviada")


async def _push(ctx, event: dict) -> None:
    """Avisa a tela aberta (WebSocket). Sem hub (linha de comando, testes), não faz nada."""
    if ctx.hub:
        await ctx.hub.broadcast(event)


def _analyst_posted(conn, day: date, settings) -> bool:
    if not settings.trigger_topic:  # 0: sem tópico de gatilho, mensagem sem tópico nunca é o post do dia
        return False
    lo, hi = _utc_bounds(day, settings.tz)
    return conn.execute("SELECT 1 FROM messages WHERE is_analyst=1 AND topic_id=? AND date_utc>=? AND date_utc<?",
                        (settings.trigger_topic, lo, hi)).fetchone() is not None


def _daily_done(conn, day: date) -> bool:
    # o veredito diário gravado também conta: um ciclo que caiu no meio não gasta IA de novo a cada 2 min
    d = day.isoformat()
    return conn.execute("SELECT 1 FROM verdicts WHERE day=? AND trigger='diario' UNION ALL "
                        "SELECT 1 FROM alerts_sent WHERE day=? AND key=?", (d, d, DONE_KEY)).fetchone() is not None


def daily_due(conn, now: datetime, settings) -> bool:
    """O ciclo do dia ainda não rodou e o analista já postou no tópico do gatilho ou passou do horário limite."""
    day = local_day(now, settings.tz)
    if _daily_done(conn, day):
        return False
    return now.astimezone(ZoneInfo(settings.tz)).hour >= settings.cutoff_hour or _analyst_posted(conn, day, settings)


async def sync_and_alert(ctx, now: datetime) -> SyncReport:
    """Sincroniza as corretoras. Falha de corretora gera um alerta por dia (chave falha:<corretora>)."""
    async def quiet(_text: str) -> None:  # o alerta sai abaixo, com o nome exato da corretora
        pass

    day = local_day(now, ctx.settings.tz)
    try:
        async with ctx.sync_lock:  # o job de 5 min e o ciclo diário não sincronizam ao mesmo tempo
            rep = await sync_all(ctx.conn, ctx.clients, quiet, now, ctx.settings.symbol_aliases)
    except UnsafeKeyError as e:  # continua recusando; o aviso sai uma vez por dia
        if alert_once(ctx.conn, day, "chave_insegura"):
            await _send(ctx, f"Chave insegura ({html.escape(str(e))}). A sincronização fica parada até a chave ser trocada "
                             "por uma somente leitura ou confirmada em config.local.toml.")
        raise
    for name, err in rep.failed.items():
        if alert_once(ctx.conn, day, f"falha:{name}"):
            await _send(ctx, format_failure(name, err))
    return rep


def mention_names(conn) -> dict[str, list[str]]:
    """Moedas da carteira mais as 100 maiores do último snapshot da CoinGecko, com o nome como apelido (Ruling R3)."""
    assets = snapshot(conn, "cg_assets", date.max) or {}
    held = {r[0] for r in conn.execute("SELECT DISTINCT symbol FROM positions WHERE qty > 0")}
    top = sorted(assets, key=lambda s: assets[s].get("rank") or math.inf)[:TOP_NAMES]
    return {s: [n] if (n := (assets.get(s) or {}).get("name")) else [] for s in held | set(top)}


HEAVY_THREAD_PREFIX = "pesado"
# executor próprio: o asyncio.run não espera estas threads ao sair (o Whisper pode levar minutos)
_HEAVY = ThreadPoolExecutor(max_workers=4, thread_name_prefix=HEAVY_THREAD_PREFIX)


def heavy_threads_running() -> list[str]:
    """Nomes das threads de trabalho pesado ainda vivas (transcrição no meio)."""
    return [t.name for t in threading.enumerate() if t.name.startswith(HEAVY_THREAD_PREFIX) and t.is_alive()]


async def in_thread(settings, fn, *args, connect=connect):
    """Roda fn(conn, *args) numa thread, com conexão própria aberta e fechada lá dentro.
    Trabalho pesado (Whisper, embeddings) não trava o loop e nunca recebe ctx.conn."""
    def work():
        conn = connect(settings.db_path)
        try:
            return fn(conn, *args)
        finally:
            conn.close()
    return await asyncio.get_running_loop().run_in_executor(_HEAVY, work)


def _index(conn, embedder) -> int:
    with _INDEX_LOCK:  # job, ciclo e mensagem do analista não indexam ao mesmo tempo os mesmos chunks
        return index_pending(conn, embedder)


async def refresh_knowledge(ctx, since_utc: datetime) -> None:
    """Indexa mensagens novas e extrai menções, para o veredito enxergar o que acabou de chegar.
    Uma falha não impede a outra etapa nem o veredito, que segue com o que já existe."""
    try:
        await in_thread(ctx.settings, _index, ctx.embedder)
    except Exception:  # banco ocupado, por exemplo
        log.exception("indexação falhou")
    try:
        async with ctx.mentions_lock:  # ciclo, mensagem do analista e job de 30 min não extraem a mesma menção duas vezes
            await run_mentions(ctx.conn, ctx.claude, mention_names(ctx.conn), ctx.settings.ambiguous_tickers, since_utc)
    except Exception:  # orçamento bloqueado ou falha da IA
        log.exception("extração de menções falhou")


def _holdings(ctx, day: date) -> tuple[dict[str, tuple[float, float]], float, list[str]]:
    """(quantidade, preço) por moeda acima da poeira, o total da carteira em US$ e os avisos de moeda sem preço."""
    coins, total, warnings = {}, 0.0, []
    for sym, qty in ctx.conn.execute("SELECT symbol, SUM(qty) FROM positions GROUP BY symbol HAVING SUM(qty) > 0"):
        try:
            price = 1.0 if sym in STABLES else last_price(ctx, sym, day)
        except ValueError as e:
            warnings.append(f"{sym}: {e}")
            continue
        total += qty * price
        if sym not in STABLES and qty * price >= ctx.settings.dust_usd:
            coins[sym] = (qty, price)
    return coins, total, warnings


def _sent(conn, day: date, key: str) -> bool:
    return conn.execute("SELECT 1 FROM alerts_sent WHERE day=? AND key=?", (day.isoformat(), key)).fetchone() is not None


def _last_verdict(conn, symbol: str) -> str | None:
    row = conn.execute("SELECT final_verdict FROM verdicts WHERE symbol=? ORDER BY id DESC LIMIT 1", (symbol,)).fetchone()
    return row[0] if row else None


def _pnl(conn, coins: dict[str, tuple[float, float]]) -> float:
    """Resultado não realizado das moedas com custo conhecido."""
    total = 0.0
    for sym, (qty, price) in coins.items():
        trades = [Trade(**{**dict(r), "ts_utc": datetime.fromisoformat(r["ts_utc"])})
                  for r in conn.execute("SELECT * FROM trades WHERE symbol=?", (sym,))]
        ov = conn.execute("SELECT avg_cost_usd FROM cost_overrides WHERE symbol=?", (sym,)).fetchone()
        total += unrealized_pnl(compute_cost_basis(trades, qty, ov[0] if ov else None), price) or 0.0
    return total


async def run_daily(ctx, day: date) -> CycleReport:
    conn, s = ctx.conn, ctx.settings
    now = datetime.now(UTC)
    await sync_and_alert(ctx, now)
    await refresh_knowledge(ctx, datetime.fromisoformat(_utc_bounds(day, s.tz)[0]))
    coins, total, warnings = _holdings(ctx, day)
    rep = CycleReport(day, warnings=warnings)
    for name in sorted(ctx.clients.keys() & UNVERIFIED):  # aviso único: a chave não muda sozinha
        key = f"permissoes:{name}"
        if not conn.execute("SELECT 1 FROM alerts_sent WHERE key=?", (key,)).fetchone() and alert_once(conn, day, key):
            rep.warnings.append(f"{name}: permissões da chave confirmadas por você no site, não pela API")
    if s.trigger_topic and not _analyst_posted(conn, day, s):  # sem tópico de gatilho não há post a esperar
        rep.warnings.insert(0, f"{subject(s)} não postou até {s.cutoff_hour}h")
    prev = {sym: _last_verdict(conn, sym) for sym in coins}
    small = [x for x, (q, p) in coins.items() if q * p < SMALL_SHARE * total] if len(coins) > BATCH_ABOVE else []
    for sym in coins:
        if sym in small:
            continue
        try:
            rep.verdicts.append(await decide(ctx, sym, day, "diario", use_ai=True))
        except Exception as e:  # noqa: BLE001 (uma moeda sem preço, por exemplo, não derruba o ciclo)
            log.warning("veredito de %s falhou: %s", sym, e)
            rep.warnings.append(f"{sym}: {e}")
    if small:
        try:
            rep.verdicts += await decide_many(ctx, small, day, "diario")
        except Exception as e:
            log.exception("lote de moedas pequenas falhou")
            rep.warnings.append(f"lote de moedas pequenas: {e}")
    rep.changed = [r for r in rep.verdicts if prev[r.symbol] not in (None, r.final_verdict)]
    alert_once(conn, day, DONE_KEY)
    await _send(ctx, format_daily(rep, total, _pnl(conn, coins), month_spent(conn, now, s.tz)))
    await _push(ctx, {"type": "cycle", "day": day.isoformat()})
    return rep


async def run_daily_if_due(ctx, now: datetime) -> CycleReport | None:
    if not daily_due(ctx.conn, now, ctx.settings):
        return None
    day = local_day(now, ctx.settings.tz)
    if not ctx.conn.execute("SELECT 1 FROM snapshots WHERE day=?", (day.isoformat(),)).fetchone():
        try:  # a coleta das 3h se perde com o Mac dormindo: o ciclo não roda com mercado velho
            await collect_and_check(ctx, day)
        except Exception:
            log.exception("coleta antes do ciclo falhou")
    return await run_daily(ctx, day)


async def _recalc_and_alert(ctx, symbol: str, day: date, trigger: str, use_ai: bool, reason: str) -> bool:
    """Recalcula a moeda e avisa se o veredito final mudou. Cada evento já passa uma vez só
    (analista:<msg_id>, movimento:<symbol>, tag:<symbol>), então dois eventos que mudam o veredito geram dois avisos.
    Devolve falso se o recálculo falhou."""
    prev = _last_verdict(ctx.conn, symbol)
    try:
        rec = await decide(ctx, symbol, day, trigger, use_ai)
    except Exception as e:  # noqa: BLE001 (falha de uma moeda não derruba o gatilho das outras)
        log.warning("recálculo de %s (%s) falhou: %s", symbol, trigger, e)
        return False
    await _push(ctx, {"type": "verdict", "symbol": symbol})
    if prev not in (None, rec.final_verdict):
        await _send(ctx, format_change(prev, rec, reason))
    return True


async def on_analyst_message(ctx, row: MessageRow) -> None:
    """Mensagem nova do analista que cita moeda da carteira: recalcula a moeda com o Claude e avisa se mudou."""
    conn, s = ctx.conn, ctx.settings
    day = local_day(datetime.fromisoformat(row.date_utc), s.tz)
    if not row.is_analyst or not alert_once(conn, day, f"analista:{row.msg_id}"):
        return  # edição da mesma mensagem não recalcula de novo
    if s.trigger_topic and row.topic_id == s.trigger_topic and not _daily_done(conn, day):
        return  # é o post do dia: o ciclo diário cobre todas as moedas
    await refresh_knowledge(ctx, datetime.fromisoformat(row.date_utc))
    coins, _, _ = _holdings(ctx, day)
    names = mention_names(conn)
    cited = find_symbols(row.text or "", {c: names.get(c, []) for c in coins}, s.ambiguous_tickers)
    cited |= {r[0] for r in conn.execute("SELECT symbol FROM mentions WHERE msg_id=? AND is_analyst=1",
                                         (row.msg_id,))} & coins.keys()  # foto sem legenda
    for sym in sorted(cited):
        await _recalc_and_alert(ctx, sym, day, "analista", True, f"{subject(s)} falou de {sym}.")


async def check_intraday(ctx, now: datetime) -> None:
    """Preço ao vivo contra o fechamento do dia anterior. Acima do limite: régua recalculada uma vez por dia."""
    conn, s = ctx.conn, ctx.settings
    day = local_day(now, s.tz)
    coins, _, _ = _holdings(ctx, day)
    for sym in coins:
        price, closes = ctx.book.last(sym), daily_closes(conn, sym, day - timedelta(days=1))
        prev_close = closes[max(closes)] if closes else None
        if not (price and prev_close) or abs(price / prev_close - 1) <= s.intraday_move:
            continue
        key = f"movimento:{sym}"
        if _sent(conn, day, key):
            continue  # já recalculado hoje: sem isso, um veredito novo a cada 5 min
        move = price / prev_close - 1
        if await _recalc_and_alert(ctx, sym, day, "movimento", False,
                                   f"{sym} {'subiu' if move > 0 else 'caiu'} {fmt_num(abs(move) * 100)}% desde o "
                                   f"fechamento de ontem ({_usd(prev_close)} para {_usd(price)})."):
            alert_once(conn, day, key)  # só depois do recálculo: se falhou, a próxima checagem tenta de novo


async def check_delisting(ctx, day: date) -> None:
    """Compara o snapshot de deslistagem do dia com o anterior. Tag nova ou corretora a menos: régua recalculada."""
    conn = ctx.conn
    row = conn.execute("SELECT 1 FROM snapshots WHERE key='delisting' AND day=?", (day.isoformat(),)).fetchone()
    if not row:
        return
    today = snapshot(conn, "delisting", day) or {}
    before = snapshot(conn, "delisting", day - timedelta(days=1)) or {}
    coins, _, _ = _holdings(ctx, day)
    for sym in coins:
        new, old = today.get(sym) or {}, before.get(sym) or {}
        reasons = []
        if new.get("monitoring_tag") and not old.get("monitoring_tag"):
            reasons.append(f"{sym} recebeu a Monitoring Tag da Binance.")
        if "listed_on" in new and old.get("listed_on") and new["listed_on"] < old["listed_on"]:
            reasons.append(f"{sym} saiu de corretora: agora em {new['listed_on']}, antes em {old['listed_on']}.")
        key = f"tag:{sym}"
        if reasons and not _sent(conn, day, key) and await _recalc_and_alert(ctx, sym, day, "tag", False,
                                                                             " ".join(reasons)):
            alert_once(conn, day, key)


async def collect_and_check(ctx, day: date) -> None:
    rep = await collect_daily(ctx.conn, ctx.http, ctx.clients, ctx.settings, day)
    if rep.failed:
        log.warning("coleta do dia com falhas: %s", ", ".join(rep.failed))
    await check_delisting(ctx, day)

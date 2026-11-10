"""Linha de comando `quilate`: instalação passo a passo e o servidor que liga todas as partes."""
import argparse
import asyncio
import logging
import os
import signal
import sys
import webbrowser
from contextlib import AsyncExitStack
from datetime import UTC, datetime, timedelta
from getpass import getpass

import httpx
import uvicorn

from quilate.ai.claude import Claude, InvalidOutput
from quilate.ai.claude import make_client as make_anthropic
from quilate.ai.playbook import build_initial, estimate_initial
from quilate.api.app import PORT, create_app
from quilate.api.hub import Hub
from quilate.api.setup import RESTART_ENV, exec_self, missing_for_serve
from quilate.config import load_settings
from quilate.context import AppContext
from quilate.cycle import heavy_threads_running, local_day, on_analyst_message, run_daily
from quilate.db import connect, migrate
from quilate.exchanges.client import NAMES, UNVERIFIED, UnconfirmedKeyError, UnsafeKeyError, make_clients
from quilate.exchanges.live import PriceBook, Tick, run_live
from quilate.knowledge.embed import Embedder
from quilate.market.collect import STABLES
from quilate.scheduler import GROUP_START, TelegramSource, schedule_history, start_scheduler
from quilate.secrets import SECRET_NAMES, MissingSecret, require_secret, set_secret
from quilate.telegram.bot import Bot, usd
from quilate.telegram.collector import MessageRow, backfill, listen, resolve_analyst_id
from quilate.telegram.collector import make_client as make_tg_client

log = logging.getLogger(__name__)
HOST = "127.0.0.1"
LIVE_RECHECK = 300  # s: refaz a assinatura de preços quando a carteira muda (a 1ª sincronização vem depois)
RECONNECT_MIN, RECONNECT_MAX = 1, 300  # s: espera entre tentativas de conectar ao Telegram


def _need(name: str) -> str:
    try:
        return require_secret(name)
    except MissingSecret as e:
        sys.exit(str(e))


def _refusal(e: UnsafeKeyError) -> str:
    """Motivo da recusa para o dono. Chave não confirmada pede confirmação, não troca de chave."""
    if isinstance(e, UnconfirmedKeyError):
        return f"Chave não confirmada: {e}."
    return f"Chave insegura: {e}. Troque por uma chave somente leitura."


def _open_db(settings):
    # 0o700: a pasta guarda a carteira e as mensagens do grupo, outra conta do Mac não pode ler
    settings.data_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    settings.data_dir.chmod(0o700)  # pasta criada antes com a permissão padrão
    conn = connect(settings.db_path)
    migrate(conn)
    return conn


async def _close_all(clients: dict) -> None:
    for c in clients.values():
        try:
            await c.close()
        except Exception:
            log.warning("%s: falha ao fechar a conexão", c.name, exc_info=True)


async def _say(text: str) -> None:
    print(text)


async def _tg_connect(settings):
    for name in ("telegram_api_id", "telegram_api_hash"):
        _need(name)
    client = make_tg_client(settings)
    await client.connect()
    if not await client.is_user_authorized():
        await client.disconnect()
        sys.exit("Sessão do Telegram ausente ou expirada. Rode: quilate telegram-login")
    return client


async def _check_keys(clients: dict) -> list[str]:
    """Uma linha por corretora. UnsafeKeyError sobe: chave que permite trade ou saque para tudo."""
    lines = []
    for name in NAMES:
        if name not in clients:
            lines.append(f"{name}: sem chave no Keychain")
            continue
        try:
            await clients[name].check_read_only()
            lines.append(f"{name}: somente leitura confirmada pelo dono (a API não informa as permissões)"
                         if name in UNVERIFIED else f"{name}: ok")
        except UnsafeKeyError:
            raise
        except Exception as e:  # só o tipo: a mensagem do ccxt pode trazer a URL assinada
            lines.append(f"{name}: falha ao verificar ({type(e).__name__})")
    return lines


async def _context(stack: AsyncExitStack, settings, hub=None) -> AppContext:
    conn = _open_db(settings)
    stack.callback(conn.close)
    clients = make_clients(settings)
    stack.push_async_callback(_close_all, clients)
    http = httpx.AsyncClient(timeout=30)
    stack.push_async_callback(http.aclose)
    bot = Bot(http, _need("telegram_bot_token"), int(_need("telegram_chat_id")))
    _need("anthropic_api_key")
    claude = Claude(make_anthropic(), conn, settings, bot.send)
    return AppContext(settings, conn, clients, PriceBook(), claude, Embedder(), http, bot, hub)  # Embedder carrega no 1º uso


def _live_symbols(conn) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for ex, sym in conn.execute("SELECT DISTINCT exchange, symbol FROM positions WHERE qty > 0 ORDER BY exchange, symbol"):
        if sym not in STABLES:
            out.setdefault(ex, []).append(sym)
    return out


async def _pause(stop: asyncio.Event, seconds: float) -> None:
    """Espera `seconds` ou até o stop, o que vier antes."""
    try:
        await asyncio.wait_for(stop.wait(), seconds)
    except TimeoutError:
        pass


async def _live(ctx, on_tick, stop: asyncio.Event) -> None:
    """Preço ao vivo das moedas da carteira. Reinicia o feed quando a lista de moedas muda."""
    while not stop.is_set():
        symbols, inner = _live_symbols(ctx.conn), asyncio.Event()
        feed = asyncio.create_task(run_live(ctx.clients, symbols, ctx.book, on_tick, inner))
        while not stop.is_set() and _live_symbols(ctx.conn) == symbols:
            await _pause(stop, LIVE_RECHECK)
        inner.set()
        await feed


async def _telegram(ctx, sched, tg, group_id: int, on_new, stop: asyncio.Event) -> None:
    """Conecta e escuta o grupo. Falha ou queda do Telegram não derruba o servir: tenta de novo com espera
    de 1 s a 300 s. O analista e o job do histórico são resolvidos na primeira conexão."""
    s, wait, analyst_id = ctx.settings, RECONNECT_MIN, None
    while not stop.is_set():
        try:
            await tg.connect()
            if not await tg.is_user_authorized():
                raise RuntimeError("sessão ausente ou expirada, rode quilate telegram-login")
            if analyst_id is None:
                analyst_id = await resolve_analyst_id(tg, s.analyst_username)
                schedule_history(sched, ctx, TelegramSource(tg, group_id, analyst_id, GROUP_START))
            log.info("Telegram conectado, escutando o grupo")
            wait = RECONNECT_MIN
            await listen(tg, ctx.conn, group_id, s.media_dir, analyst_id, on_new)
            log.warning("Telegram desconectou")
        except Exception as e:
            log.warning("Telegram indisponível (%s: %s)", type(e).__name__, e)
        if stop.is_set():
            break
        log.info("nova tentativa de conectar ao Telegram em %s s", wait)
        await _pause(stop, wait)
        wait = min(wait * 2, RECONNECT_MAX)


async def _setup_context(stack: AsyncExitStack, settings) -> AppContext:
    """Contexto do modo instalação: banco e HTTP, sem corretora, IA, bot nem Telegram."""
    conn = _open_db(settings)
    stack.callback(conn.close)
    http = httpx.AsyncClient(timeout=30)
    stack.push_async_callback(http.aclose)
    return AppContext(settings, conn, {}, PriceBook(), None, None, http, None, Hub())


async def _serve(settings, port: int) -> bool:
    """Sobe a API. Devolve True quando a página Configuração pediu o reinício.

    Sem os segredos obrigatórios o servidor fica no modo instalação: só a API e a página, para gravar o que falta
    (decisão R47). Com tudo gravado, liga corretoras, agendador e Telegram.
    """
    async with AsyncExitStack() as stack:
        # SIGTERM (launchctl bootout, logout) vira SystemExit, que desfaz a pilha e fecha tudo. O uvicorn
        # guarda o sinal durante o serve() e o reenvia depois. Sem handler, o processo morreria sem fechar nada.
        stack.callback(signal.signal, signal.SIGTERM, signal.signal(signal.SIGTERM, lambda *_: sys.exit(0)))
        missing = missing_for_serve(settings)
        if missing:
            url = f"http://{HOST}:{port}/configuracao"
            log.warning("modo instalação: falta %s. Complete em %s", ", ".join(missing), url)
            ctx = await _setup_context(stack, settings)
            app = create_app(ctx, port=port)
            if not os.environ.get(RESTART_ENV):  # no reinício a página já está aberta
                webbrowser.open(url)
        else:
            ctx = await _context(stack, settings, Hub())
            try:
                for line in await _check_keys(ctx.clients):
                    log.info("checar-chaves: %s", line)
            except UnsafeKeyError as e:
                sys.exit(f"{_refusal(e)} O servidor não subiu.")
            app = create_app(ctx, port=port)
            group_id = int(_need("telegram_group_id"))
            tg = make_tg_client(settings)
            stack.push_async_callback(tg.disconnect)
            sched = start_scheduler(ctx)  # o job do histórico entra quando o Telegram conectar
            stack.callback(sched.shutdown, wait=False)

            async def on_tick(t: Tick) -> None:  # o PriceBook já foi atualizado por run_live
                await ctx.hub.broadcast({"type": "tick", "symbol": t.symbol, "price_usd": t.last, "ts": t.ts_ms})

            async def on_new(row: MessageRow) -> None:
                if row.is_analyst:
                    await on_analyst_message(ctx, row)

            stop = asyncio.Event()
            live = asyncio.create_task(_live(ctx, on_tick, stop))
            listener = asyncio.create_task(_telegram(ctx, sched, tg, group_id, on_new, stop))

            async def stop_tasks() -> None:
                stop.set()
                listener.cancel()
                await asyncio.gather(live, listener, return_exceptions=True)

            stack.push_async_callback(stop_tasks)
        server = uvicorn.Server(uvicorn.Config(app, host=HOST, port=port, log_level="info"))
        ctx.stop_server = lambda: setattr(server, "should_exit", True)
        await server.serve()
        return ctx.restart_requested


async def _telegram_login(settings) -> None:
    for name in ("telegram_api_id", "telegram_api_hash"):
        _need(name)
    client = make_tg_client(settings)  # StringSession: nada é gravado em disco
    try:
        await client.start()  # pede telefone, código e senha de duas etapas no terminal
        set_secret("telegram_session", client.session.save())
        me = await client.get_me()
        print(f"Sessão de @{me.username} gravada no Keychain.")
    finally:
        await client.disconnect()


async def _check_keys_cmd(settings) -> None:
    clients = make_clients(settings)
    try:
        try:
            lines = await _check_keys(clients)
        except UnsafeKeyError as e:
            sys.exit(_refusal(e))
    finally:
        await _close_all(clients)
    print("\n".join(lines))
    if any("falha" in line for line in lines):
        sys.exit(1)


async def _import(settings, months: int) -> None:
    conn = _open_db(settings)
    try:
        tg = await _tg_connect(settings)
        try:
            analyst_id = await resolve_analyst_id(tg, settings.analyst_username)
            since = datetime.now(UTC) - timedelta(days=round(months * 365 / 12))
            n = await backfill(tg, conn, int(_need("telegram_group_id")), since, settings.media_dir, analyst_id,
                               lambda k: print(f"\r{k} mensagens", end="", flush=True),
                               refresh_days=2, max_messages=None)
        finally:
            await tg.disconnect()
    finally:
        conn.close()
    print(f"\n{n} mensagens importadas desde {since:%d/%m/%Y}. O histórico mais antigo entra pelo servir, "
          "um lote por hora.")


async def _initial_playbook(settings) -> None:
    conn = _open_db(settings)
    try:
        _need("anthropic_api_key")
        claude = Claude(make_anthropic(), conn, settings, _say)
        cost = await estimate_initial(claude, conn, GROUP_START, settings)
        print(f"Estimativa do manual inicial com o Opus: {usd(cost)} (custo único, fora do limite mensal).")
        try:
            answer = input("Rodar agora? (s/n) ")
        except EOFError:  # sem terminal: vale como não
            answer = ""
        if answer.strip() not in ("s", "S"):
            print("Cancelado. Nenhuma chamada paga foi feita.")
            return
        try:
            vid = await build_initial(claude, conn, GROUP_START, settings)
        except InvalidOutput as e:  # as partes já extraídas ficaram salvas em playbook_drafts
            sys.exit(f"O manual inicial parou ({e}). Rode de novo: as partes já extraídas não são pagas outra vez.")
        print(f"Manual criado (versão {vid}). Revise e aprove as regras no dashboard.")
    finally:
        conn.close()


async def _cycle(settings) -> None:
    async with AsyncExitStack() as stack:
        ctx = await _context(stack, settings)
        try:
            rep = await run_daily(ctx, local_day(datetime.now(UTC), settings.tz))
        except UnsafeKeyError as e:
            sys.exit(_refusal(e))
    print(f"Ciclo de {rep.day:%d/%m/%Y}: {len(rep.verdicts)} vereditos, {len(rep.changed)} mudaram.")
    for w in rep.warnings:
        print(f"Aviso: {w}")


def _main(argv: list[str] | None) -> None:
    p = argparse.ArgumentParser(prog="quilate")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("segredo", help="grava um segredo no Keychain").add_argument("nome", choices=SECRET_NAMES)
    sub.add_parser("telegram-login", help="login do Telegram, sessão gravada no Keychain")
    sub.add_parser("checar-chaves", help="confere se as chaves das corretoras são somente leitura")
    sub.add_parser("importar", help="importa o histórico do grupo").add_argument("--meses", type=int, default=12)
    sub.add_parser("manual-inicial", help="estima o custo e cria o manual do analista")
    sub.add_parser("ciclo", help="roda o ciclo diário agora")
    serve = sub.add_parser("servir", help="sobe o dashboard e o agendador")
    serve.add_argument("--host", default=HOST)
    serve.add_argument("--porta", type=int, default=PORT)
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.cmd == "servir" else logging.WARNING,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    # o httpx grava a URL de cada requisição em INFO, e a URL leva o token do bot e a chave da FRED
    logging.getLogger("httpx").setLevel(logging.WARNING)

    if args.cmd == "servir" and args.host != HOST:
        sys.exit(f"Recusado: o servidor só escuta em {HOST}.")
    if args.cmd == "importar" and args.meses < 1:
        p.error("--meses precisa ser 1 ou mais")
    if args.cmd == "segredo":
        value = getpass(f"Valor de {args.nome} (não aparece na tela): ").strip()
        if not value:
            sys.exit("Valor vazio: nada foi gravado.")
        set_secret(args.nome, value)
        print(f"{args.nome} gravado no Keychain.")
        return
    try:
        settings = load_settings()
    except ValueError as e:  # chave desconhecida no config.local.toml: uma linha, sem traceback
        sys.exit(str(e))
    if args.cmd == "importar" and not settings.analyst_username:
        sys.exit("Defina analyst_username em quilate/config.local.toml ou na página Configuração.")
    restart = asyncio.run({
        "telegram-login": lambda: _telegram_login(settings),
        "checar-chaves": lambda: _check_keys_cmd(settings),
        "importar": lambda: _import(settings, args.meses),
        "manual-inicial": lambda: _initial_playbook(settings),
        "ciclo": lambda: _cycle(settings),
        "servir": lambda: _serve(settings, args.porta),
    }[args.cmd]())
    if args.cmd == "servir" and restart:
        log.info("reiniciando o servir a pedido da página Configuração")
        logging.shutdown()
        exec_self()  # troca o processo: as threads pesadas morrem com ele, o job volta como pendente
    if args.cmd == "servir" and (busy := heavy_threads_running()):
        # o Whisper pode levar minutos; o launchd mataria o processo em 20 s de qualquer jeito.
        # O SQLite em WAL aguenta o corte e o job volta como pendente na próxima rodada.
        log.info("saída imediata com %d thread(s) de trabalho pesado no meio: %s", len(busy), ", ".join(busy))
        logging.shutdown()
        os._exit(0)


def main(argv: list[str] | None = None) -> None:
    """Ctrl-C sai com uma linha e o código 130, sem traceback. Transcrição no meio não segura a saída (R42)."""
    try:
        _main(argv)
    except KeyboardInterrupt:
        cmd = (sys.argv[1:] if argv is None else argv)[:1]
        print("Servidor encerrado." if cmd == ["servir"] else "Cancelado.", file=sys.stderr)
        if busy := heavy_threads_running():
            log.info("saída imediata com %d thread(s) de trabalho pesado no meio: %s", len(busy), ", ".join(busy))
            logging.shutdown()
            os._exit(130)
        sys.exit(130)


if __name__ == "__main__":
    main()

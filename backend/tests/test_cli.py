import asyncio
import logging
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from quilate import cli
from quilate.ai.claude import Claude, InvalidOutput
from quilate.cli import main
from quilate.config import load_settings
from quilate.exchanges.client import ExchangeClient, UnsafeKeyError
from quilate.exchanges.live import Tick
from quilate.scheduler import GROUP_START, TelegramSource
from quilate.telegram.bot import Bot
from quilate.telegram.collector import MessageRow

SERVICE = "quilate"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    s = replace(load_settings(), data_dir=tmp_path / "dados", analyst_name="", analyst_username="usuario_do_analista")
    monkeypatch.setattr(cli, "load_settings", lambda: s)
    return s


def test_importar_refuses_without_analyst_username(settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "load_settings", lambda: replace(settings, analyst_username=""))
    with pytest.raises(SystemExit) as e:
        main(["importar"])
    assert "config.local.toml" in str(e.value)


def test_unknown_local_key_exits_without_traceback(monkeypatch):
    def bad():
        raise ValueError("Chave desconhecida em config.local.toml: analist_username")
    monkeypatch.setattr(cli, "load_settings", bad)
    with pytest.raises(SystemExit) as e:
        main(["ciclo"])
    assert e.value.code == "Chave desconhecida em config.local.toml: analist_username"


@pytest.fixture
def keys(memory_keyring):
    for k, v in {"telegram_bot_token": "tok", "telegram_chat_id": "42", "telegram_group_id": "-100123",
                 "anthropic_api_key": "sk-teste", "telegram_api_id": "1", "telegram_api_hash": "h"}.items():
        memory_keyring.set_password(SERVICE, k, v)
    return memory_keyring


def test_servir_exits_at_once_when_a_heavy_thread_is_still_running(settings, monkeypatch):
    """R42: transcrição no meio do SIGTERM não segura a saída; o job volta como pendente."""
    import threading

    from quilate import cycle
    stop = threading.Event()
    t = threading.Thread(target=stop.wait, name=f"{cycle.HEAVY_THREAD_PREFIX}_teste", daemon=True)
    t.start()
    exited = []
    monkeypatch.setattr(cli.asyncio, "run", lambda coro: coro.close())
    monkeypatch.setattr(cli.os, "_exit", lambda code: exited.append(code))
    try:
        assert cycle.heavy_threads_running() == [t.name]
        main(["servir"])
        assert exited == [0]
    finally:
        stop.set()
        t.join()
    main(["servir"])  # sem thread pesada: saída normal
    assert exited == [0]


def test_serve_refuses_other_host():
    with pytest.raises(SystemExit):
        main(["servir", "--host", "0.0.0.0"])


def test_secret_name_must_be_known():
    with pytest.raises(SystemExit):
        main(["segredo", "qualquer"])


def test_segredo_stores_without_echo(memory_keyring, settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "getpass", lambda prompt: "valor-secreto")
    main(["segredo", "fred_key"])
    assert memory_keyring.store[(SERVICE, "fred_key")] == "valor-secreto"
    assert "valor-secreto" not in capsys.readouterr().out


class FakeManual:
    def __init__(self):
        self.build_calls = 0

    async def estimate(self, claude, conn, since_utc, settings):
        return 3.2

    async def build(self, claude, conn, since_utc, settings):
        self.build_calls += 1
        return 1


@pytest.fixture
def fake_manual(monkeypatch, keys, settings):
    fake = FakeManual()
    monkeypatch.setattr(cli, "make_anthropic", lambda: object())
    monkeypatch.setattr(cli, "estimate_initial", fake.estimate)
    monkeypatch.setattr(cli, "build_initial", fake.build)
    return fake


def test_manual_inicial_aborts_on_no(monkeypatch, capsys, fake_manual):
    monkeypatch.setattr("builtins.input", lambda _: "n")
    main(["manual-inicial"])
    assert "US$ 3,20" in capsys.readouterr().out and fake_manual.build_calls == 0


def test_manual_inicial_cut_consolidation_says_how_to_resume(monkeypatch, fake_manual):
    async def cut(claude, conn, since_utc, settings):
        raise InvalidOutput("resposta cortada no limite de 64000 tokens")

    monkeypatch.setattr(cli, "build_initial", cut)
    monkeypatch.setattr("builtins.input", lambda prompt: "s")
    with pytest.raises(SystemExit) as e:
        main(["manual-inicial"])
    assert "Rode de novo" in str(e.value) and "64000" in str(e.value)


def test_manual_inicial_runs_on_yes(monkeypatch, fake_manual):
    monkeypatch.setattr("builtins.input", lambda _: "S")
    main(["manual-inicial"])
    assert fake_manual.build_calls == 1


class FakeTg:
    def __init__(self, authorized=True, fail=0):
        self.connected, self.authorized, self.started, self.fail, self.connects = False, authorized, False, fail, 0
        self.gone = asyncio.Event()
        self.session = SimpleNamespace(save=lambda: "1sessao-em-texto")

    async def connect(self):
        self.connects += 1
        if self.fail:
            self.fail -= 1
            raise ConnectionError("sem rede")
        self.connected = True

    def is_connected(self):
        return self.connected

    async def is_user_authorized(self):
        return self.authorized

    async def start(self):
        self.started = True

    async def get_me(self):
        return SimpleNamespace(username="demo_user")

    async def disconnect(self):
        self.connected = False
        self.gone.set()


def test_telegram_login_stores_string_session(keys, settings, monkeypatch, capsys):
    tg = FakeTg()
    monkeypatch.setattr(cli, "make_tg_client", lambda s: tg)
    main(["telegram-login"])
    assert tg.started and not tg.connected
    assert keys.store[(SERVICE, "telegram_session")] == "1sessao-em-texto"
    assert "1sessao-em-texto" not in capsys.readouterr().out


def test_string_session_writes_no_file(tmp_path, monkeypatch, keys):
    monkeypatch.chdir(tmp_path)
    from quilate.telegram.collector import make_client
    client = make_client(None)
    client.session.save()
    assert list(tmp_path.rglob("*.session*")) == []


def test_importar_backfills_requested_months(keys, settings, monkeypatch, capsys):
    tg, calls = FakeTg(), []

    async def fake_backfill(client, conn, group_id, since_utc, media_dir, analyst_id, on_progress, **kw):
        calls.append((group_id, since_utc, analyst_id, kw))
        on_progress(1)
        return 1

    async def analyst(client, username):
        assert username == "usuario_do_analista"
        return 7

    monkeypatch.setattr(cli, "make_tg_client", lambda s: tg)
    monkeypatch.setattr(cli, "resolve_analyst_id", analyst)
    monkeypatch.setattr(cli, "backfill", fake_backfill)
    main(["importar", "--meses", "12"])
    (group_id, since, analyst_id, kw), = calls
    assert group_id == -100123 and analyst_id == 7
    assert kw == {"refresh_days": 2, "max_messages": None}
    assert abs(datetime.now(UTC) - timedelta(days=365) - since) < timedelta(minutes=1)
    assert not tg.connected and "1 mensagens" in capsys.readouterr().out


def test_importar_without_session_points_to_login(keys, settings, monkeypatch):
    monkeypatch.setattr(cli, "make_tg_client", lambda s: FakeTg(authorized=False))
    with pytest.raises(SystemExit) as e:
        main(["importar"])
    assert "telegram-login" in str(e.value.code)


class FakeExchange:
    def __init__(self, name="binance", unsafe=False):
        self.name, self.unsafe, self.closed = name, unsafe, False

    async def check_read_only(self):
        if self.unsafe:
            raise UnsafeKeyError("binance: a chave permite trade ou saque")

    async def close(self):
        self.closed = True


def test_checar_chaves_reports_each_exchange(keys, settings, monkeypatch, capsys):
    ex = FakeExchange()
    monkeypatch.setattr(cli, "make_clients", lambda s: {"binance": ex})
    main(["checar-chaves"])
    out = capsys.readouterr().out
    assert "binance: ok" in out and "mexc: sem chave" in out and ex.closed


class NoPermissionApi:
    async def close(self):
        pass


def test_checar_chaves_refuses_unconfirmed_mexc(keys, settings, monkeypatch):
    monkeypatch.setattr(cli, "make_clients", lambda s: {"mexc": ExchangeClient("mexc", NoPermissionApi())})
    with pytest.raises(SystemExit) as e:
        main(["checar-chaves"])
    msg = str(e.value.code)
    assert "mexc" in msg and "confirmed_read_only" in msg and "config.local.toml" in msg


def test_checar_chaves_accepts_confirmed_mexc(keys, settings, monkeypatch, capsys):
    monkeypatch.setattr(cli, "make_clients",
                        lambda s: {"mexc": ExchangeClient("mexc", NoPermissionApi(), confirmed=True)})
    main(["checar-chaves"])
    assert "mexc: somente leitura confirmada pelo dono" in capsys.readouterr().out


def test_main_keeps_httpx_urls_out_of_the_log(keys, settings, monkeypatch, caplog):
    # o httpx grava a URL em INFO: o token do bot e a chave da FRED iriam para o log do servir
    caplog.set_level(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.NOTSET)  # sem depender do import de market/collect.py
    monkeypatch.setattr(cli, "make_clients", lambda s: {})
    main(["checar-chaves"])
    assert logging.getLogger("httpx").level == logging.WARNING
    logging.getLogger("httpx").info("HTTP Request: POST https://api.telegram.org/bot123:FAKE/sendMessage")
    assert "FAKE" not in caplog.text


def test_data_dir_is_private(settings):
    cli._open_db(settings).close()
    assert settings.data_dir.stat().st_mode & 0o777 == 0o700
    settings.data_dir.chmod(0o755)  # pasta criada antes da correção
    cli._open_db(settings).close()
    assert settings.data_dir.stat().st_mode & 0o777 == 0o700


class FakeServer:
    last = None

    def __init__(self, config):
        self.config = config
        FakeServer.last = self

    async def serve(self):
        await FakeServer.listening.wait()  # a escuta do grupo começou
        row = lambda analyst: MessageRow(1, 1, 7, "usuario_do_analista", analyst, "2026-11-04T12:00:00+00:00",  # noqa: E731
                                         "ARB", None, None, None)
        await self.on_new(row(1))
        await self.on_new(row(0))


@pytest.fixture
def serve_fakes(keys, settings, monkeypatch):
    f = SimpleNamespace(ex=FakeExchange(), tg=FakeTg(), ws=[], routed=[], scheduled=[], live_symbols=[],
                        shutdown=[], ctx=None)
    FakeServer.last, FakeServer.listening = None, asyncio.Event()

    class WS:
        async def send_json(self, event):
            f.ws.append(event)

    real_create_app = cli.create_app

    def create_app(ctx, port):
        f.ctx, f.port = ctx, port
        ctx.hub.add(WS())
        return real_create_app(ctx, port=port)

    async def analyst(client, username):
        return 7

    def start_scheduler(ctx, telegram=None):
        assert telegram is None  # o Telegram conecta depois, sem segurar o agendador
        return SimpleNamespace(shutdown=lambda wait: f.shutdown.append(wait))

    def schedule_history(sched, ctx, telegram):
        f.scheduled.append(telegram)

    async def run_live(clients, symbols, book, on_tick, stop):
        f.live_symbols.append(symbols)
        await on_tick(Tick("binance", "ARB", 0.5, 1))
        await stop.wait()

    async def listen(client, conn, group_id, media_dir, analyst_id, on_new):
        FakeServer.on_new = staticmethod(on_new)
        FakeServer.listening.set()
        await client.gone.wait()

    async def on_analyst(ctx, row):
        f.routed.append(row)

    monkeypatch.setattr(cli, "make_clients", lambda s: {"binance": f.ex})
    monkeypatch.setattr(cli, "make_tg_client", lambda s: f.tg)
    monkeypatch.setattr(cli, "make_anthropic", lambda: object())
    monkeypatch.setattr(cli, "create_app", create_app)
    monkeypatch.setattr(cli, "resolve_analyst_id", analyst)
    monkeypatch.setattr(cli, "start_scheduler", start_scheduler)
    monkeypatch.setattr(cli, "schedule_history", schedule_history)
    monkeypatch.setattr(cli, "run_live", run_live)
    monkeypatch.setattr(cli, "listen", listen)
    monkeypatch.setattr(cli, "on_analyst_message", on_analyst)
    monkeypatch.setattr(cli.uvicorn, "Server", FakeServer)
    settings.data_dir.mkdir(parents=True)
    from quilate.db import connect, migrate
    conn = connect(settings.db_path)
    migrate(conn)
    conn.execute("INSERT INTO positions VALUES ('binance','ARB','spot',10,'2026-11-04',0)")
    conn.execute("INSERT INTO positions VALUES ('binance','USDT','spot',10,'2026-11-04',0)")
    conn.commit()
    conn.close()
    return f


def test_servir_wires_everything_and_shuts_down_clean(serve_fakes):
    f = serve_fakes
    main(["servir"])
    cfg = FakeServer.last.config
    assert (cfg.host, cfg.port) == ("127.0.0.1", 8000)
    assert isinstance(f.ctx.bot, Bot) and isinstance(f.ctx.claude, Claude)
    assert f.ctx.embedder._model is None  # o modelo só carrega no primeiro uso
    assert f.scheduled == [TelegramSource(f.tg, -100123, 7, GROUP_START)]
    assert GROUP_START == datetime(2015, 1, 1, tzinfo=UTC)
    assert f.live_symbols == [{"binance": ["ARB"]}]  # stablecoin fora do feed
    assert f.ws == [{"type": "tick", "symbol": "ARB", "price_usd": 0.5, "ts": 1}]
    assert [r.is_analyst for r in f.routed] == [1]  # só a mensagem do analista vai para o ciclo
    assert f.ex.closed and not f.tg.connected and f.ctx.http.is_closed and f.shutdown == [False]
    with pytest.raises(sqlite3.ProgrammingError):
        f.ctx.conn.execute("SELECT 1")


def test_servir_other_port_reaches_the_allowlist(serve_fakes):
    main(["servir", "--porta", "8123"])
    assert FakeServer.last.config.port == serve_fakes.port == 8123


def test_servir_stops_on_unsafe_key(serve_fakes):
    serve_fakes.ex.unsafe = True
    with pytest.raises(SystemExit) as e:
        main(["servir"])
    assert "permite trade ou saque" in str(e.value.code)
    assert FakeServer.last is None and serve_fakes.ex.closed


async def test_live_feed_restarts_when_portfolio_changes(db, monkeypatch):
    started, recheck = asyncio.Queue(), asyncio.Queue()

    async def run_live(clients, symbols, book, on_tick, stop):
        await started.put(symbols)
        await stop.wait()

    async def pause(stop, seconds):  # cada recheck só acontece quando o teste libera
        await recheck.get()

    async def nop(t):
        pass

    monkeypatch.setattr(cli, "run_live", run_live)
    monkeypatch.setattr(cli, "_pause", pause)
    ctx, stop = SimpleNamespace(conn=db, clients={}, book=None), asyncio.Event()
    task = asyncio.create_task(cli._live(ctx, nop, stop))
    assert await started.get() == {}
    db.execute("INSERT INTO positions VALUES ('mexc','SOL','spot',1,'2026-11-04',0)")  # 1ª sincronização
    db.commit()
    await recheck.put(None)
    assert await started.get() == {"mexc": ["SOL"]}
    stop.set()
    await recheck.put(None)
    await task


@pytest.fixture
def tg_loop(db, monkeypatch):
    f = SimpleNamespace(delays=[], listens=0, scheduled=[], resolves=0, stop=asyncio.Event(), returns=0)

    async def pause(stop, seconds):
        f.delays.append(seconds)

    async def analyst(client, username):
        f.resolves += 1
        return 7

    async def listen(client, conn, group_id, media_dir, analyst_id, on_new):
        f.listens += 1
        if f.listens > f.returns:
            f.stop.set()  # fim do teste
        client.connected = False  # run_until_disconnected voltou: queda da conexão

    monkeypatch.setattr(cli, "_pause", pause)
    monkeypatch.setattr(cli, "resolve_analyst_id", analyst)
    monkeypatch.setattr(cli, "listen", listen)
    monkeypatch.setattr(cli, "schedule_history", lambda sched, ctx, tg: f.scheduled.append(tg))
    f.ctx = SimpleNamespace(conn=db, settings=replace(load_settings(), analyst_name="", analyst_username="usuario_do_analista"))
    return f


async def nop_new(row):
    pass


async def test_telegram_connect_fails_twice_then_listens(tg_loop):
    f, tg = tg_loop, FakeTg(fail=2)
    await cli._telegram(f.ctx, None, tg, -100123, nop_new, f.stop)
    assert tg.connects == 3 and f.delays == [1, 2] and f.listens == 1
    assert f.scheduled == [TelegramSource(tg, -100123, 7, GROUP_START)]


async def test_telegram_reconnects_after_listen_returns(tg_loop):
    f, tg = tg_loop, FakeTg()
    f.returns = 1
    await cli._telegram(f.ctx, None, tg, -100123, nop_new, f.stop)
    assert tg.connects == 2 and f.listens == 2 and f.delays == [1]
    assert f.resolves == 1 and len(f.scheduled) == 1  # analista e job do histórico uma vez só


async def test_stop_ends_telegram_loop_during_backoff(db):
    tried, stop = asyncio.Event(), asyncio.Event()

    class Down(FakeTg):
        async def connect(self):
            tried.set()
            raise ConnectionError("sem rede")

    task = asyncio.create_task(cli._telegram(SimpleNamespace(conn=db, settings=replace(load_settings(), analyst_name="", analyst_username="usuario_do_analista")), None, Down(), 1,
                                             nop_new, stop))
    await tried.wait()  # agora está na espera de 1 s
    stop.set()
    await asyncio.wait_for(task, 0.5)  # guarda: sem o stop, a espera seria de 1 s


def test_manual_inicial_without_tty_aborts(monkeypatch, fake_manual):
    def no_tty(_):
        raise EOFError

    monkeypatch.setattr("builtins.input", no_tty)
    main(["manual-inicial"])
    assert fake_manual.build_calls == 0


SIGTERM_SCRIPT = r"""
import asyncio, sys
from dataclasses import replace
from pathlib import Path
import keyring
out = Path(sys.argv[1])
sys.path.insert(0, sys.argv[2])
from conftest import MemoryKeyring
from quilate import cli
from quilate.config import load_settings

kr = MemoryKeyring()
keyring.set_keyring(kr)
for k, v in {"telegram_bot_token": "tok", "telegram_chat_id": "42", "telegram_group_id": "-1",
             "anthropic_api_key": "k", "telegram_api_id": "1", "telegram_api_hash": "h"}.items():
    kr.set_password("quilate", k, v)
settings = replace(load_settings(), data_dir=out / "dados", analyst_name="", analyst_username="usuario_do_analista")  # sem depender do config.local.toml

def mark(text):
    with open(out / "marcas", "a") as fh:
        fh.write(text + "\n")

class Ex:
    name = "binance"
    async def check_read_only(self): pass
    async def close(self): mark("ccxt fechado")

class Tg:
    connected = False
    async def connect(self): self.connected = True
    async def is_user_authorized(self): return True
    def is_connected(self): return self.connected
    async def disconnect(self): mark("telegram fechado")

async def analyst(client, username): return 7
async def listen(*a): await asyncio.Event().wait()
async def run_live(clients, symbols, book, on_tick, stop): await stop.wait()

cli.load_settings = lambda: settings
cli.make_clients = lambda s: {"binance": Ex()}
cli.make_tg_client = lambda s: Tg()
cli.make_anthropic = lambda: object()
cli.resolve_analyst_id = analyst
cli.listen = listen
cli.run_live = run_live
cli.start_scheduler = lambda ctx, telegram=None: type("S", (), {"shutdown": lambda self, wait: mark("agendador parado")})()
cli.schedule_history = lambda sched, ctx, tg: None
cli.main(["servir", "--porta", "0"])
"""


def test_sigterm_runs_the_clean_shutdown(tmp_path):
    import signal
    import subprocess
    import sys
    from pathlib import Path
    script = tmp_path / "servir.py"
    script.write_text(SIGTERM_SCRIPT)
    proc = subprocess.Popen([sys.executable, str(script), str(tmp_path), str(Path(__file__).parent)],
                            stderr=subprocess.PIPE, text=True)
    log = []
    for line in proc.stderr:  # espera o uvicorn subir de verdade
        log.append(line)
        if "Uvicorn running on" in line:
            break
    proc.send_signal(signal.SIGTERM)  # o que o launchctl bootout e o logout enviam
    _, err = proc.communicate(timeout=30)
    assert proc.returncode == 0, "".join(log) + err
    assert set((tmp_path / "marcas").read_text().split("\n")) >= {"ccxt fechado", "telegram fechado",
                                                                   "agendador parado"}


class QuietServer:
    """uvicorn falso: só registra a configuração e devolve na hora."""
    last = None

    def __init__(self, config):
        self.config, self.should_exit = config, False
        QuietServer.last = self

    async def serve(self):
        pass


def test_servir_without_required_secrets_enters_setup_mode(settings, memory_keyring, monkeypatch, caplog):
    """R47: sem os segredos obrigatórios o servir sobe só a API e a página Configuração, e abre o navegador."""
    opened, apps = [], []
    real_create_app = cli.create_app

    def create_app(ctx, port):
        apps.append(ctx)
        return real_create_app(ctx, port=port)

    monkeypatch.setattr(cli, "create_app", create_app)
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(cli, "start_scheduler", lambda *a, **k: pytest.fail("agendador não sobe no modo instalação"))
    monkeypatch.setattr(cli.uvicorn, "Server", QuietServer)
    caplog.set_level(logging.WARNING)
    main(["servir"])
    assert opened == ["http://127.0.0.1:8000/configuracao"]
    (ctx,) = apps
    assert ctx.bot is None and ctx.clients == {} and ctx.stop_server is not None
    assert "modo instalação" in caplog.text and "anthropic_api_key" in caplog.text


def test_servir_restarts_itself_when_the_page_asks(settings, memory_keyring, monkeypatch):
    execs, ctxs = [], []
    real = cli.create_app

    def create_app(ctx, port):
        ctxs.append(ctx)
        return real(ctx, port=port)

    class AskRestart(QuietServer):
        async def serve(self):
            ctxs[0].restart_requested = True  # o que POST /api/setup/restart faz

    monkeypatch.setattr(cli.webbrowser, "open", lambda url: None)
    monkeypatch.setattr(cli, "exec_self", lambda: execs.append(True))
    monkeypatch.setattr(cli, "create_app", create_app)
    monkeypatch.setattr(cli.uvicorn, "Server", AskRestart)
    main(["servir"])
    assert execs == [True]


def test_setup_mode_after_restart_does_not_open_another_tab(settings, memory_keyring, monkeypatch):
    opened = []
    monkeypatch.setenv("QUILATE_RESTART", "1")
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: opened.append(url))
    monkeypatch.setattr(cli.uvicorn, "Server", QuietServer)
    main(["servir"])
    assert opened == []


def _ctrl_c(coro):
    coro.close()
    raise KeyboardInterrupt


def test_ctrl_c_on_servir_exits_clean_without_traceback(settings, monkeypatch, capsys):
    monkeypatch.setattr(cli.asyncio, "run", _ctrl_c)
    with pytest.raises(SystemExit) as e:
        main(["servir"])
    assert e.value.code == 130  # convenção do shell para Ctrl-C
    err = capsys.readouterr().err
    assert "Servidor encerrado." in err and "Traceback" not in err


def test_ctrl_c_with_heavy_thread_exits_at_once(settings, monkeypatch):
    """O Ctrl-C segue a regra do SIGTERM (R42): transcrição no meio não segura a saída."""
    import threading

    from quilate import cycle
    stop = threading.Event()
    t = threading.Thread(target=stop.wait, name=f"{cycle.HEAVY_THREAD_PREFIX}_teste", daemon=True)
    t.start()
    exited = []
    monkeypatch.setattr(cli.asyncio, "run", _ctrl_c)
    monkeypatch.setattr(cli.os, "_exit", lambda code: exited.append(code))
    try:
        with pytest.raises(SystemExit):
            main(["servir"])
        assert exited == [130]
    finally:
        stop.set()
        t.join()


def test_ctrl_c_while_typing_a_secret_stores_nothing(memory_keyring, monkeypatch, capsys):
    def interrupted(prompt):
        raise KeyboardInterrupt

    monkeypatch.setattr(cli, "getpass", interrupted)
    with pytest.raises(SystemExit) as e:
        main(["segredo", "binance_key"])
    assert e.value.code == 130
    assert memory_keyring.store == {}
    assert "Cancelado." in capsys.readouterr().err

"""Rotas /api/setup: estado, segredos, configuração, checagem de chaves, login do Telegram e reinício (R47)."""
import sqlite3
from dataclasses import replace
from types import SimpleNamespace

import pytest
import sqlite_vec
from fastapi.testclient import TestClient

from quilate.api import setup as setup_mod
from quilate.api.app import create_app
from quilate.api.hub import Hub
from quilate.config import DEFAULT_PATH, load_settings, save_local
from quilate.context import AppContext
from quilate.db import migrate
from quilate.exchanges.client import ExchangeClient, UnsafeKeyError
from quilate.exchanges.live import PriceBook

SERVICE = "quilate"


@pytest.fixture
def ctx(tmp_path, memory_keyring):
    conn = sqlite3.connect(tmp_path / "t.db", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    migrate(conn)
    yield AppContext(replace(load_settings(), analyst_username="", analyst_name=""), conn, {}, PriceBook(), None, None, None, None, Hub())
    conn.close()


@pytest.fixture
def client(ctx, tmp_path):
    # o router grava o config.local.toml ao lado de um config.toml de teste, nunca o do pacote
    base = tmp_path / "config.toml"
    base.write_text("")
    app = create_app(ctx, static_dir=tmp_path / "sem-front", local_config=base)
    return TestClient(app, base_url="http://127.0.0.1:8000", headers={"host": "127.0.0.1:8000"}), base


def test_status_lists_secrets_without_values_and_a_checklist(client, memory_keyring):
    c, _ = client
    memory_keyring.set_password(SERVICE, "binance_key", "k-super-secreta")
    memory_keyring.set_password(SERVICE, "binance_secret", "s-super-secreta")
    r = c.get("/api/setup")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "setup"
    assert body["secrets"]["binance_key"] is True and body["secrets"]["anthropic_api_key"] is False
    assert "k-super-secreta" not in r.text and "s-super-secreta" not in r.text
    steps = {s["id"]: s for s in body["checklist"]}
    assert steps["corretoras"]["done"] and not steps["analista"]["done"] and not steps["claude"]["done"]
    assert steps["confirmacao"]["done"]  # Binance não precisa de confirmação
    assert steps["importar"]["how"].endswith("importar --meses 12")
    assert body["missing_for_serve"] == [*setup_mod.REQUIRED_SECRETS, "analyst_username"]


def test_secret_goes_to_keychain_and_never_comes_back(client, memory_keyring, caplog):
    c, _ = client
    r = c.post("/api/setup/secrets/anthropic_api_key", json={"value": " sk-valor-secreto "})
    assert r.status_code == 200 and r.json() == {"ok": True, "name": "anthropic_api_key"}
    assert memory_keyring.store[(SERVICE, "anthropic_api_key")] == "sk-valor-secreto"
    assert "sk-valor-secreto" not in caplog.text
    assert c.post("/api/setup/secrets/nao_existe", json={"value": "x"}).status_code == 404
    assert c.post("/api/setup/secrets/anthropic_api_key", json={"value": ""}).status_code == 422
    assert c.delete("/api/setup/secrets/anthropic_api_key").json() == {"ok": True, "name": "anthropic_api_key"}
    assert (SERVICE, "anthropic_api_key") not in memory_keyring.store


def test_secret_write_needs_a_local_origin(client, memory_keyring):
    c, _ = client
    r = c.post("/api/setup/secrets/anthropic_api_key", json={"value": "x"}, headers={"origin": "https://evil.example"})
    assert r.status_code == 403 and (SERVICE, "anthropic_api_key") not in memory_keyring.store


def test_config_is_saved_to_local_toml_and_applied(client, ctx):
    c, base = client
    (base.with_name("config.local.toml")).write_text('analyst_username = "antigo"\n\n[group_topics]\n1 = "GERAL"\n')
    r = c.put("/api/setup/config", json={"owner_name": "Dana", "analyst_username": "@usuario_do_analista", "sync_minutes": 10,
                                          "confirmed_read_only": ["gate", "mexc", "gate"]})
    assert r.status_code == 200
    body = r.json()
    assert body["restart_required"] is True
    assert body["config"]["analyst_username"] == "usuario_do_analista" and body["config"]["confirmed_read_only"] == ["gate", "mexc"]
    assert ctx.settings.owner_name == "Dana" and ctx.settings.sync_minutes == 10
    text = base.with_name("config.local.toml").read_text()
    assert 'analyst_username = "usuario_do_analista"' in text and "sync_minutes = 10" in text
    assert 'confirmed_read_only = ["gate", "mexc"]' in text and '[group_topics]\n1 = "GERAL"' in text
    assert c.put("/api/setup/config", json={"confirmed_read_only": ["binance"]}).status_code == 422
    assert c.put("/api/setup/config", json={"sync_minutes": 0}).status_code == 422
    assert c.put("/api/setup/config", json={}).status_code == 422


def test_budget_change_applies_without_restart(client, ctx):
    c, _ = client
    r = c.put("/api/setup/config", json={"budget_usd": 20, "intraday_move": 0.05})
    assert r.json()["restart_required"] is False and ctx.settings.budget_usd == 20


def test_save_local_round_trips_through_load_settings(tmp_path):
    base = tmp_path / "config.toml"
    base.write_text(DEFAULT_PATH.read_text())
    save_local({"owner_name": 'Vi "T" \\ ó', "sync_minutes": 7, "confirmed_read_only": ["mexc"]}, base)
    s = load_settings(base)
    assert s.owner_name == 'Vi "T" \\ ó' and s.sync_minutes == 7 and s.confirmed_read_only == {"mexc"}


class FakeApi:
    def __init__(self, unsafe=False):
        self.unsafe, self.closed = unsafe, False

    async def sapi_get_account_apirestrictions(self):
        return {"enableReading": True, "enableWithdrawals": self.unsafe, "enableSpotAndMarginTrading": False,
                "enableMargin": False, "enableFutures": False, "permitsUniversalTransfer": False,
                "enableInternalTransfer": False, "enableVanillaOptions": False, "enablePortfolioMarginTrading": False,
                "enableFixApiTrade": False, "enableFixReadOnly": False}

    async def close(self):
        self.closed = True


def test_check_keys_reports_each_exchange(client, monkeypatch):
    c, _ = client
    good, bad, unconfirmed = FakeApi(), FakeApi(unsafe=True), FakeApi()
    monkeypatch.setattr(setup_mod, "make_clients", lambda s: {
        "binance": ExchangeClient("binance", good), "mexc": ExchangeClient("mexc", unconfirmed),
        "bybit": ExchangeClient("bybit", SimpleNamespace(private_get_v5_user_query_api=bad.sapi_get_account_apirestrictions,
                                                          close=bad.close))})
    r = c.post("/api/setup/check-keys")
    assert r.status_code == 200
    by = {x["exchange"]: x["status"] for x in r.json()["exchanges"]}
    assert by == {"binance": "ok", "mexc": "unconfirmed", "bybit": "unsafe", "gate": "missing"}
    assert r.json()["safe"] is False and good.closed and unconfirmed.closed


def test_check_keys_marks_unsafe_binance(client, monkeypatch):
    c, _ = client
    monkeypatch.setattr(setup_mod, "make_clients", lambda s: {"binance": ExchangeClient("binance", FakeApi(unsafe=True))})
    assert {x["exchange"]: x["status"] for x in c.post("/api/setup/check-keys").json()["exchanges"]}["binance"] == "unsafe"
    assert isinstance(UnsafeKeyError("x"), Exception)


class FakeTg:
    def __init__(self, needs_password=False):
        self.needs_password, self.connected, self.signed = needs_password, False, []
        self.session = SimpleNamespace(save=lambda: "1sessao-em-texto")

    async def connect(self):
        self.connected = True

    async def send_code_request(self, phone):
        self.phone = phone
        return SimpleNamespace(phone_code_hash="h1")

    async def sign_in(self, phone=None, code=None, phone_code_hash=None, password=None):
        from telethon.errors import SessionPasswordNeededError
        self.signed.append((phone, code, phone_code_hash, password))
        if self.needs_password and password is None:
            raise SessionPasswordNeededError(None)

    async def get_me(self):
        return SimpleNamespace(username="demo_user")

    async def disconnect(self):
        self.connected = False


def test_telegram_login_by_page_stores_session(client, memory_keyring, monkeypatch):
    c, _ = client
    tg = FakeTg(needs_password=True)
    monkeypatch.setattr(setup_mod, "make_tg_client", lambda s: tg)
    assert c.post("/api/setup/telegram/send-code", json={"phone": "+55 11 99999 0000"}).status_code == 409  # sem api_id
    memory_keyring.set_password(SERVICE, "telegram_api_id", "1")
    memory_keyring.set_password(SERVICE, "telegram_api_hash", "h")
    assert c.post("/api/setup/telegram/sign-in", json={"code": "12345"}).status_code == 409  # sem pedir o código
    assert c.post("/api/setup/telegram/send-code", json={"phone": "+55 11 99999 0000"}).json() == {"ok": True}
    assert c.post("/api/setup/telegram/sign-in", json={"code": "12345"}).json() == {"ok": False, "needs_password": True}
    r = c.post("/api/setup/telegram/sign-in", json={"code": "12345", "password": "senha-2fa"})
    assert r.json() == {"ok": True, "username": "demo_user"}
    assert memory_keyring.store[(SERVICE, "telegram_session")] == "1sessao-em-texto"
    assert tg.signed == [("+55 11 99999 0000", "12345", "h1", None), (None, None, None, "senha-2fa")]
    assert not tg.connected and "senha-2fa" not in r.text


def test_restart_asks_the_server_to_stop(client, ctx):
    c, _ = client
    assert c.post("/api/setup/restart").status_code == 409  # fora do servir
    stopped = []
    ctx.stop_server = lambda: stopped.append(True)
    assert c.post("/api/setup/restart").json() == {"ok": True}
    assert stopped == [True] and ctx.restart_requested is True
    assert c.get("/api/setup").json()["restart_required"] is True

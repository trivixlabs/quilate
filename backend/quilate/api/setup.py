"""Rotas `/api/setup/*` da página Configuração. Só em 127.0.0.1, como o resto da API.

Segredo entra por POST e vai direto ao Keychain. Nunca volta na resposta, nunca vai para o log (decisão R47).
A API só diz se cada segredo existe. Nada aqui gasta dinheiro nem toca a carteira.
"""
import logging
import os
import sys
from dataclasses import replace
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from quilate.ai.playbook import current_playbook
from quilate.config import LOCAL_KEYS, save_local
from quilate.exchanges.client import NAMES, UNVERIFIED, UnconfirmedKeyError, UnsafeKeyError, make_clients
from quilate.secrets import SECRET_NAMES, delete_secret, has_secret, set_secret
from quilate.telegram.collector import make_client as make_tg_client

log = logging.getLogger(__name__)

# Sem estes o `servir` fica no modo instalação: só a API e a página, sem agendador, corretora ou Telegram.
REQUIRED_SECRETS = ("anthropic_api_key", "telegram_api_id", "telegram_api_hash", "telegram_group_id",
                    "telegram_bot_token", "telegram_chat_id")
MARKET_KEYS = ("coingecko_key", "coinalyze_key", "fred_key")  # coinglass_key é opcional (R: custo medido antes)
IMPORT_CMD = "cd ~/quilate/backend && uv run quilate importar --meses 12"
PLAYBOOK_CMD = "cd ~/quilate/backend && uv run quilate manual-inicial"


def missing_for_serve(settings) -> list[str]:
    out = [n for n in REQUIRED_SECRETS if not has_secret(n)]
    if not settings.analyst_username:
        out.append("analyst_username")
    return out


class SecretBody(BaseModel):
    value: str = Field(min_length=1, max_length=4096)


class ConfigBody(BaseModel):
    """Todos opcionais: só o que vier é gravado."""
    owner_name: str | None = Field(None, max_length=80)
    analyst_username: str | None = Field(None, max_length=64, pattern=r"^@?[A-Za-z0-9_]*$")
    analyst_name: str | None = Field(None, max_length=80)
    confirmed_read_only: list[str] | None = None
    budget_usd: float | None = Field(None, gt=0, le=10_000, allow_inf_nan=False)
    budget_alert_ratio: float | None = Field(None, gt=0, lt=1, allow_inf_nan=False)
    dust_usd: float | None = Field(None, ge=0, le=10_000, allow_inf_nan=False)
    cutoff_hour: int | None = Field(None, ge=0, le=23)
    intraday_move: float | None = Field(None, gt=0, le=1, allow_inf_nan=False)
    sync_minutes: int | None = Field(None, ge=1, le=60)


class PhoneBody(BaseModel):
    phone: str = Field(min_length=8, max_length=20, pattern=r"^\+?[0-9 ]+$")


class SignInBody(BaseModel):
    code: str = Field(min_length=1, max_length=10)
    password: str | None = Field(None, max_length=256)


def setup_router(ctx, local_path: Path | None = None) -> APIRouter:
    r = APIRouter(prefix="/api/setup")
    login: dict = {}  # login do Telegram em andamento: cliente conectado, telefone e hash do código

    def config_view(s) -> dict:
        return {"owner_name": s.owner_name, "analyst_username": s.analyst_username,
                "analyst_name": s.analyst_name,
                "confirmed_read_only": sorted(s.confirmed_read_only), "budget_usd": s.budget_usd,
                "budget_alert_ratio": s.budget_alert_ratio, "dust_usd": s.dust_usd, "cutoff_hour": s.cutoff_hour,
                "intraday_move": s.intraday_move, "sync_minutes": s.sync_minutes, "tz": s.tz,
                "data_dir": str(s.data_dir)}

    def count(table: str) -> int:
        return ctx.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608 nome fixo

    def checklist(s, secrets: dict[str, bool], data: dict, mode: str) -> list[dict]:
        with_keys = [n for n in NAMES if secrets[f"{n}_key"] and secrets[f"{n}_secret"]]
        pending_confirm = [n for n in with_keys if n in UNVERIFIED and n not in s.confirmed_read_only]
        every = lambda *names: all(secrets[n] for n in names)  # noqa: E731
        return [
            {"id": "analista", "label": "Usuário do analista no Telegram", "done": bool(s.analyst_username),
             "how": "Quem publica as análises no grupo, sem @."},
            {"id": "corretoras", "label": "Chave somente leitura de pelo menos uma corretora", "done": bool(with_keys),
             "how": "Crie a chave no site da corretora, sem trade nem saque, e grave aqui."},
            {"id": "confirmacao", "label": "MEXC e Gate confirmadas como somente leitura", "done": not pending_confirm,
             "how": f"Pendente: {', '.join(pending_confirm)}. Confira no site e marque a confirmação." if pending_confirm
             else "Só vale para MEXC e Gate, que não informam a permissão pela API."},
            {"id": "telegram_app", "label": "Aplicativo do Telegram (api_id, api_hash e id do grupo)",
             "done": every("telegram_api_id", "telegram_api_hash", "telegram_group_id"),
             "how": "Crie o aplicativo em my.telegram.org e informe o id do grupo."},
            {"id": "telegram_login", "label": "Login do Telegram (sessão no Keychain)", "done": secrets["telegram_session"],
             "how": "Telefone, código e senha de duas etapas."},
            {"id": "bot", "label": "Bot dos avisos (token e chat)", "done": every("telegram_bot_token", "telegram_chat_id"),
             "how": "Bot criado no @BotFather e o id do seu chat com ele."},
            {"id": "claude", "label": "Chave da API do Claude", "done": secrets["anthropic_api_key"],
             "how": "Chave criada no console da Anthropic."},
            {"id": "mercado", "label": "Chaves de dados de mercado (CoinGecko, Coinalyze, FRED)", "done": every(*MARKET_KEYS),
             "how": "Planos gratuitos bastam. A CoinGlass é opcional."},
            {"id": "hf", "label": "Token do Hugging Face (licença do EmbeddingGemma aceita)", "done": secrets["hf_token"],
             "how": "Aceite a licença do google/embeddinggemma-300m e crie um token de leitura."},
            {"id": "importar", "label": "Histórico do grupo importado", "done": data["messages"] > 0,
             "how": f"No terminal: {IMPORT_CMD}"},
            {"id": "manual", "label": "Manual inicial do analista criado", "done": data["playbook"],
             "how": f"No terminal, confirma o custo antes de gastar: {PLAYBOOK_CMD}"},
            {"id": "servir", "label": "Servidor completo no ar (agendador, corretoras e Telegram)", "done": mode == "full",
             "how": "Com os segredos obrigatórios gravados, use Reiniciar o servidor."},
        ]

    @r.get("")
    async def status():
        s = ctx.settings
        secrets = {n: has_secret(n) for n in SECRET_NAMES}
        data = {"messages": count("messages"), "trades": count("trades"), "positions": count("positions"),
                "verdicts": count("verdicts"), "playbook": current_playbook(ctx.conn) is not None}
        mode = "setup" if ctx.clients is None or ctx.bot is None else "full"
        return {"mode": mode, "secrets": secrets, "config": config_view(s), "data": data,
                "checklist": checklist(s, secrets, data, mode), "restart_required": ctx.restart_requested,
                "missing_for_serve": missing_for_serve(s), "required_secrets": list(REQUIRED_SECRETS)}

    @r.post("/secrets/{name}")
    async def put_secret(name: str, body: SecretBody):
        if name not in SECRET_NAMES:
            raise HTTPException(404, "Segredo desconhecido.")
        set_secret(name, body.value.strip())
        log.info("segredo %s gravado pela página Configuração", name)  # só o nome
        return {"ok": True, "name": name}

    @r.delete("/secrets/{name}")
    async def drop_secret(name: str):
        if name not in SECRET_NAMES:
            raise HTTPException(404, "Segredo desconhecido.")
        delete_secret(name)
        return {"ok": True, "name": name}

    @r.put("/config")
    async def put_config(body: ConfigBody):
        changes = {k: v for k, v in body.model_dump().items() if v is not None and k in LOCAL_KEYS}
        if "analyst_username" in changes:
            changes["analyst_username"] = changes["analyst_username"].lstrip("@")
        if "confirmed_read_only" in changes:
            bad = sorted(set(changes["confirmed_read_only"]) - set(UNVERIFIED))
            if bad:
                raise HTTPException(422, f"Só MEXC e Gate precisam de confirmação. Recusado: {', '.join(bad)}.")
            changes["confirmed_read_only"] = sorted(set(changes["confirmed_read_only"]))
        if not changes:
            raise HTTPException(422, "Nada para gravar.")
        save_local(changes, local_path)
        new = replace(ctx.settings, **{k: (frozenset(v) if k == "confirmed_read_only" else v) for k, v in changes.items()})
        # agendador e clientes das corretoras leem a configuração ao subir: estes só valem depois do reinício
        needs_restart = any(k in changes for k in ("sync_minutes", "confirmed_read_only", "analyst_username"))
        ctx.settings = new
        ctx.restart_requested = ctx.restart_requested or needs_restart
        return {"ok": True, "config": config_view(new), "restart_required": ctx.restart_requested}

    @r.post("/check-keys")
    async def check_keys():
        """Abre clientes só com as chaves do Keychain, confere e fecha. Não usa os clientes do servir."""
        clients = make_clients(ctx.settings)
        out = []
        try:
            for name in NAMES:
                if name not in clients:
                    out.append({"exchange": name, "status": "missing", "detail": "sem chave no Keychain"})
                    continue
                try:
                    await clients[name].check_read_only()
                    out.append({"exchange": name, "status": "ok", "detail": "somente leitura confirmada pelo dono"
                                if name in UNVERIFIED else "somente leitura confirmada pela API"})
                except UnconfirmedKeyError:
                    out.append({"exchange": name, "status": "unconfirmed",
                                "detail": "a API não informa a permissão: confira no site e marque a confirmação"})
                except UnsafeKeyError:
                    out.append({"exchange": name, "status": "unsafe",
                                "detail": "a chave permite trade, saque ou transferência: troque por uma só de leitura"})
                except Exception as e:  # só o tipo: a mensagem do ccxt pode trazer a URL assinada
                    out.append({"exchange": name, "status": "error", "detail": f"falha ao verificar ({type(e).__name__})"})
        finally:
            for c in clients.values():
                try:
                    await c.close()
                except Exception:
                    log.warning("%s: falha ao fechar", c.name, exc_info=True)
        return {"exchanges": out, "safe": all(x["status"] in ("ok", "missing") for x in out)}

    @r.post("/telegram/send-code")
    async def telegram_send_code(body: PhoneBody):
        for n in ("telegram_api_id", "telegram_api_hash"):
            if not has_secret(n):
                raise HTTPException(409, f"Grave {n} antes do login.")
        if old := login.pop("client", None):
            await old.disconnect()
        client = make_tg_client(ctx.settings)
        try:
            await client.connect()
            sent = await client.send_code_request(body.phone)
        except Exception as e:
            await client.disconnect()
            raise HTTPException(502, f"O Telegram não aceitou o pedido ({type(e).__name__}).") from e
        login.update(client=client, phone=body.phone, hash=sent.phone_code_hash)
        return {"ok": True}

    @r.post("/telegram/sign-in")
    async def telegram_sign_in(body: SignInBody):
        client = login.get("client")
        if client is None:
            raise HTTPException(409, "Peça o código antes.")
        from telethon.errors import SessionPasswordNeededError
        try:
            if body.password:
                await client.sign_in(password=body.password)
            else:
                await client.sign_in(login["phone"], body.code, phone_code_hash=login["hash"])
        except SessionPasswordNeededError:
            return {"ok": False, "needs_password": True}
        except Exception as e:
            raise HTTPException(401, f"O Telegram recusou ({type(e).__name__}).") from e
        set_secret("telegram_session", client.session.save())
        me = await client.get_me()
        await client.disconnect()
        login.clear()
        return {"ok": True, "username": getattr(me, "username", None)}

    @r.post("/restart")
    async def restart():
        """Encerra o uvicorn. O `main` do servir troca o processo pelo mesmo comando (R47)."""
        if ctx.stop_server is None:
            raise HTTPException(409, "Fora do servir não há o que reiniciar.")
        ctx.restart_requested = True
        ctx.stop_server()
        return {"ok": True}

    return r


RESTART_ENV = "QUILATE_RESTART"  # marca o processo que veio de um reinício: o navegador já está aberto


def exec_self() -> None:
    """Troca o processo pelo mesmo comando, com os mesmos argumentos. Chamado pelo `main` depois do servir."""
    os.environ[RESTART_ENV] = "1"
    os.execv(sys.executable, [sys.executable, "-m", "quilate.cli", *sys.argv[1:]])

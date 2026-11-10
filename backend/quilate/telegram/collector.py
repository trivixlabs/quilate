"""Coletor do grupo do Telegram. Só lê: nenhuma função aqui escreve no grupo."""
import asyncio
import logging
import re
import sqlite3
from collections.abc import Awaitable, Callable
from dataclasses import astuple, dataclass, fields
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from quilate.secrets import get_secret

_URL = re.compile(r"https?://\S+")
log = logging.getLogger(__name__)


def _is_youtube(url: str) -> bool:
    host = urlparse(url).hostname or ""
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


@dataclass
class MessageRow:
    msg_id: int
    topic_id: int
    author_id: int | None
    author_username: str | None
    is_analyst: int
    date_utc: str
    text: str
    reply_to: int | None
    edited_utc: str | None
    media_kind: str | None
    media_path: str | None = None


def topic_of(msg) -> int:
    """Tópico do fórum: reply_to_top_id; senão reply_to_msg_id se forum_topic; senão 1 (Geral)."""
    r = msg.reply_to
    if r is None:
        return 1
    if r.reply_to_top_id:
        return r.reply_to_top_id
    if r.forum_topic and r.reply_to_msg_id:
        return r.reply_to_msg_id
    return 1


def extract_links(text: str) -> list[str]:
    return [u.rstrip(".,;:!?)]}>\"'") for u in _URL.findall(text or "")]


def _media_kind(msg) -> str | None:
    if msg.photo:
        return "foto"
    if msg.voice or msg.audio:
        return "audio"
    if msg.video:
        return "video"
    if msg.document:
        return "documento"
    return None


def _iso(d: datetime) -> str:
    return d.astimezone(UTC).isoformat()


def to_row(msg, analyst_id: int) -> MessageRow:
    return MessageRow(
        msg_id=msg.id, topic_id=topic_of(msg), author_id=msg.sender_id,
        author_username=getattr(msg.sender, "username", None),
        is_analyst=int(msg.sender_id == analyst_id), date_utc=_iso(msg.date),
        text=msg.message or "", reply_to=msg.reply_to.reply_to_msg_id if msg.reply_to else None,
        edited_utc=_iso(msg.edit_date) if msg.edit_date else None, media_kind=_media_kind(msg),
    )


async def _flood_safe(call):
    """Executa `call()` e, se o Telegram mandar esperar, dorme o tempo pedido e repete."""
    while True:
        try:
            return await call()
        except FloodWaitError as e:
            await asyncio.sleep(e.seconds)


_COLS = [f.name for f in fields(MessageRow)]
_UPSERT = (
    f"INSERT INTO messages ({','.join(_COLS)}) VALUES ({','.join('?' * len(_COLS))}) "
    "ON CONFLICT(msg_id) DO UPDATE SET text=excluded.text, edited_utc=excluded.edited_utc, "
    "media_kind=excluded.media_kind, media_path=COALESCE(excluded.media_path, media_path)"
)


def _queue(conn: sqlite3.Connection, kind: str, ref: str, msg_id: int) -> None:
    conn.execute("INSERT OR IGNORE INTO media_jobs (kind, ref, msg_id) VALUES (?,?,?)", (kind, ref, msg_id))


async def _ingest(msg, conn: sqlite3.Connection, media_dir: Path, analyst_id: int) -> MessageRow:
    row = to_row(msg, analyst_id)
    have = conn.execute("SELECT media_path FROM messages WHERE msg_id=?", (row.msg_id,)).fetchone()
    if have and have[0]:
        row.media_path = have[0]  # retomada: não baixa de novo
    elif row.media_kind == "foto" or (row.media_kind == "audio" and row.is_analyst):
        media_dir.mkdir(parents=True, exist_ok=True)
        try:
            got = await _flood_safe(lambda: msg.download_media(file=str(media_dir / str(row.msg_id))))
            row.media_path = str(got) if got else None
        except Exception:
            log.exception("falha ao baixar mídia da mensagem %s", row.msg_id)  # tenta de novo na próxima
    conn.execute(_UPSERT, astuple(row))
    if row.media_kind == "audio" and row.is_analyst and row.media_path:
        _queue(conn, "audio", row.media_path, row.msg_id)
    if row.is_analyst:
        for url in extract_links(row.text):
            _queue(conn, "youtube" if _is_youtube(url) else "link", url, row.msg_id)
    conn.commit()
    return row


async def backfill(client, conn: sqlite3.Connection, group_id: int, since_utc: datetime,
                   media_dir: Path, analyst_id: int, on_progress: Callable[[int], None],
                   refresh_days: int = 2, max_messages: int | None = None,
                   now: datetime | None = None) -> int:
    """1) Reescaneia a janela recente (pega edições). 2) Continua o histórico a partir da mais velha
    gravada até since_utc. Nunca reescaneia o meio. max_messages limita o lote."""
    n = 0

    async def walk(offset_id: int, keep: Callable[[object], bool], limit: int | None) -> None:
        """Grava mensagens enquanto keep(msg) valer, até `limit` (None = sem teto)."""
        nonlocal n
        done = 0
        while True:
            try:
                async for msg in client.iter_messages(group_id, offset_id=offset_id):
                    if not keep(msg) or (limit is not None and done >= limit):
                        return
                    await _ingest(msg, conn, media_dir, analyst_id)
                    n, done, offset_id = n + 1, done + 1, msg.id
                    on_progress(n)
                return
            except FloodWaitError as e:
                await asyncio.sleep(e.seconds)  # retoma de offset_id

    floor = max((now or datetime.now(UTC)) - timedelta(days=refresh_days), since_utc)
    top = conn.execute("SELECT max(msg_id) FROM messages").fetchone()[0]
    # Fase 1 (sem teto): janela recente + lacuna acima do maior id gravado (queda longa).
    await walk(0, lambda m: m.date >= floor or (top is not None and m.id > top and m.date >= since_utc), None)
    # Fase 2 (com teto): histórico a partir da mais velha gravada.
    oldest = conn.execute("SELECT min(msg_id) FROM messages").fetchone()[0] or 0
    await walk(oldest, lambda m: m.date >= since_utc, max_messages)
    return n


async def listen(client, conn: sqlite3.Connection, group_id: int, media_dir: Path, analyst_id: int,
                 on_new: Callable[[MessageRow], Awaitable[None]]) -> None:
    async def handler(event) -> None:
        row = await _ingest(event.message, conn, media_dir, analyst_id)
        await on_new(row)

    client.add_event_handler(handler, events.NewMessage(chats=group_id))
    client.add_event_handler(handler, events.MessageEdited(chats=group_id))
    try:
        await client.run_until_disconnected()
    finally:  # numa reconexão, listen roda de novo: sem isso cada mensagem seria gravada duas vezes
        client.remove_event_handler(handler)


async def resolve_analyst_id(client, username: str) -> int:
    return (await client.get_entity(username)).id


def make_client(settings) -> TelegramClient:
    return TelegramClient(
        StringSession(get_secret("telegram_session") or ""),
        int(get_secret("telegram_api_id")), get_secret("telegram_api_hash"),
    )

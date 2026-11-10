from datetime import UTC, datetime, timedelta
from types import SimpleNamespace as NS

from telethon.errors import FloodWaitError
from telethon.sessions import StringSession

from quilate.telegram.collector import (
    backfill,
    extract_links,
    listen,
    make_client,
    resolve_analyst_id,
    to_row,
    topic_of,
)

SINCE = datetime(2024, 1, 1, tzinfo=UTC)
DATE = datetime(2025, 3, 1, 12, 0, tzinfo=UTC)
NOW = DATE + timedelta(hours=1)


def fake_msg(id, text="", photo=False, voice=False, video=False, document=False,
             reply_top=None, reply_msg=None, forum_topic=False, sender="fulano", sender_id=1,
             date=DATE, edit_date=None):
    reply = None
    if reply_top is not None or reply_msg is not None:
        reply = NS(reply_to_top_id=reply_top, reply_to_msg_id=reply_msg, forum_topic=forum_topic)
    m = NS(id=id, message=text, date=date, sender_id=sender_id, sender=NS(username=sender),
           photo=object() if photo else None, voice=object() if voice else None, audio=None,
           video=object() if video else None, document=object() if document else None,
           reply_to=reply, edit_date=edit_date, downloads=[])

    async def download_media(file):
        m.downloads.append(file)
        return f"{file}.jpg"
    m.download_media = download_media
    return m


class FakeTg:
    def __init__(self, msgs):
        self.msgs = {m.id: m for m in msgs}
        self.handlers = []
        self.flood = 0
        self.calls = []
        self.yielded = []

    def edit(self, id, text):
        self.msgs[id].message = text

    async def iter_messages(self, group_id, offset_id=0, **kw):
        self.calls.append(offset_id)
        for m in sorted(self.msgs.values(), key=lambda m: -m.id):
            if offset_id and m.id >= offset_id:
                continue
            if self.flood and m.id == 1:
                self.flood -= 1
                raise FloodWaitError(request=None, capture=7)
            self.yielded.append(m.id)
            yield m

    def add_event_handler(self, cb, ev):
        self.handlers.append(cb)

    def remove_event_handler(self, cb):
        self.removed = getattr(self, "removed", 0) + sum(h is cb for h in self.handlers)

    async def run_until_disconnected(self):
        pass

    async def get_entity(self, username):
        return NS(id=99, username=username)


def test_row_from_photo_message():
    r = to_row(fake_msg(id=7, text="BTC no suporte", photo=True, reply_top=101,
                        sender="usuario_do_analista", sender_id=99), analyst_id=99)
    assert (r.msg_id, r.topic_id, r.is_analyst, r.media_kind) == (7, 101, 1, "foto")


def test_general_topic_when_no_reply():
    assert topic_of(fake_msg(id=8, reply_top=None)) == 1


def test_topic_from_forum_reply_without_top():
    assert topic_of(fake_msg(id=9, reply_msg=555, forum_topic=True)) == 555
    assert topic_of(fake_msg(id=9, reply_msg=555)) == 1  # resposta comum no General


def test_media_kinds():
    k = lambda **kw: to_row(fake_msg(id=1, **kw), 99).media_kind
    assert (k(voice=True), k(video=True), k(document=True), k()) == ("audio", "video", "documento", None)


def test_extract_links_strips_punctuation():
    assert extract_links("veja https://youtu.be/abc123, e (http://x.com/a).") == [
        "https://youtu.be/abc123", "http://x.com/a"]


async def test_backfill_twice_no_duplicates_and_edit_updates(db, tmp_path):
    client = FakeTg([fake_msg(id=1, text="a"), fake_msg(id=2, text="b")])
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    client.edit(2, "b editada")
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 2
    assert db.execute("SELECT text FROM messages WHERE msg_id=2").fetchone()[0] == "b editada"


async def test_backfill_stops_at_since_and_reports_progress(db, tmp_path):
    old = datetime(2023, 1, 1, tzinfo=UTC)
    client = FakeTg([fake_msg(id=1, date=old), fake_msg(id=2), fake_msg(id=3)])
    seen = []
    n = await backfill(client, db, 1, SINCE, tmp_path, 99, seen.append, now=NOW)
    assert n == 2 and seen[-1] == 2
    assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 2


async def test_backfill_downloads_photo_once_and_analyst_audio_queues_job(db, tmp_path):
    photo, voice = fake_msg(id=1, photo=True), fake_msg(id=2, voice=True, sender_id=99)
    member = fake_msg(id=3, voice=True, sender_id=5)
    client = FakeTg([photo, voice, member])
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    assert photo.downloads == [str(tmp_path / "1")] and len(voice.downloads) == 1
    assert db.execute("SELECT media_path FROM messages WHERE msg_id=1").fetchone()[0].endswith("1.jpg")
    jobs = db.execute("SELECT kind, status, msg_id FROM media_jobs").fetchall()
    assert [tuple(j) for j in jobs] == [("audio", "pendente", 2)]
    assert member.downloads == []
    assert tuple(db.execute("SELECT media_kind, media_path FROM messages WHERE msg_id=3").fetchone()) == ("audio", None)


async def test_backfill_survives_flood_wait(db, tmp_path, monkeypatch):
    slept = []

    async def fake_sleep(s):
        slept.append(s)
    monkeypatch.setattr("quilate.telegram.collector.asyncio.sleep", fake_sleep)
    client = FakeTg([fake_msg(id=1), fake_msg(id=2)])
    client.flood = 1
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    assert slept == [7]
    assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 2


async def test_links_queue_media_jobs_only_for_analyst(db, tmp_path):
    client = FakeTg([
        fake_msg(id=1, text="olha https://youtu.be/abc e https://site.com/x", sender_id=99),
        fake_msg(id=2, text="https://youtu.be/zzz", sender_id=5),
    ])
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    rows = db.execute("SELECT kind, ref, status, msg_id FROM media_jobs ORDER BY id").fetchall()
    assert [tuple(r) for r in rows] == [
        ("youtube", "https://youtu.be/abc", "pendente", 1),
        ("link", "https://site.com/x", "pendente", 1)]


async def test_listen_inserts_and_calls_on_new_for_new_and_edit(db, tmp_path):
    client = FakeTg([])
    got = []

    async def on_new(row):
        got.append((row.msg_id, row.text))
    await listen(client, db, 1, tmp_path, 99, on_new)
    assert len(client.handlers) == 2 and client.removed == 2  # tirados quando a conexão cai
    h = client.handlers[0]
    await h(NS(message=fake_msg(id=5, text="oi", sender_id=99)))
    await h(NS(message=fake_msg(id=5, text="oi editado", sender_id=99)))
    assert got == [(5, "oi"), (5, "oi editado")]
    assert db.execute("SELECT text FROM messages WHERE msg_id=5").fetchone()[0] == "oi editado"


async def test_resolve_analyst_id():
    assert await resolve_analyst_id(FakeTg([]), "usuario_do_analista") == 99


def test_make_client_uses_string_session(memory_keyring):
    from quilate.secrets import set_secret
    set_secret("telegram_api_id", "123")
    set_secret("telegram_api_hash", "abc")
    set_secret("telegram_session", "")
    c = make_client(None)
    assert c.api_id == 123
    assert isinstance(c.session, StringSession)


def test_collector_never_sends():
    import inspect

    import quilate.telegram.collector as mod
    src = inspect.getsource(mod)
    assert not any(w in src for w in ("send_message", "send_file", "edit_message", "delete_messages"))


OLD = DATE - timedelta(days=30)


async def test_second_run_does_not_refetch_middle(db, tmp_path):
    client = FakeTg([fake_msg(id=i, date=OLD) for i in (1, 2, 3)] + [fake_msg(id=4), fake_msg(id=5)])
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    client.yielded.clear()
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    assert not {1, 2} & set(client.yielded)  # 3 só aparece como limite da janela


async def test_continues_past_oldest_stored_in_batches(db, tmp_path):
    client = FakeTg([fake_msg(id=i, date=OLD) for i in range(1, 7)])
    for expected_min in (5, 3, 1):
        await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, max_messages=2, now=NOW)
        assert db.execute("SELECT min(msg_id) FROM messages").fetchone()[0] == expected_min
    assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 6


async def test_gap_after_long_downtime_is_filled(db, tmp_path):
    ten = DATE - timedelta(days=10)
    client = FakeTg([fake_msg(id=1, date=ten), fake_msg(id=2, date=ten)])
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=ten)
    for i in (3, 4, 5):  # chegaram durante a queda de 5+ dias
        client.msgs[i] = fake_msg(id=i, date=DATE - timedelta(days=5))
    client.msgs[6] = fake_msg(id=6)
    client.yielded.clear()
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    assert {r[0] for r in db.execute("SELECT msg_id FROM messages")} == {1, 2, 3, 4, 5, 6}
    assert 1 not in client.yielded


async def test_recent_window_does_not_starve_history(db, tmp_path):
    recent = [fake_msg(id=i) for i in range(10, 16)]
    old = [fake_msg(id=i, date=OLD) for i in range(1, 6)]
    client = FakeTg(recent + old)
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, max_messages=2, now=NOW)
    assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 8  # 6 recentes + 2 de histórico
    assert db.execute("SELECT min(msg_id) FROM messages").fetchone()[0] == 4


def test_youtube_host_variants():
    from quilate.telegram.collector import _is_youtube
    assert all(_is_youtube(u) for u in ("https://youtu.be/a", "https://music.youtube.com/x", "https://youtube.com/x"))
    assert not _is_youtube("https://notyoutube.com/x")


async def test_bad_download_does_not_abort_batch(db, tmp_path):
    bad = fake_msg(id=1, photo=True)

    async def boom(file):
        raise OSError("disco")
    bad.download_media = boom
    client = FakeTg([bad, fake_msg(id=2, photo=True)])
    await backfill(client, db, 1, SINCE, tmp_path, 99, lambda n: None, now=NOW)
    assert db.execute("SELECT count(*) FROM messages").fetchone()[0] == 2

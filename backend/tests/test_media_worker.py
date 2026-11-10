
import sys
import types

import pytest
import respx

from quilate.media.links import fetch_text
from quilate.media.transcribe import Segment
from quilate.media.worker import process_jobs
from quilate.media.youtube import download_audio


def add_job(db, kind, ref, msg_id):
    db.execute(
        "INSERT OR IGNORE INTO messages (msg_id, date_utc, text) VALUES (?, ?, '')",
        (msg_id, f"2026-01-{msg_id:02d}T10:00:00+00:00"),
    )
    db.execute("INSERT INTO media_jobs (kind, ref, msg_id) VALUES (?,?,?)", (kind, ref, msg_id))
    db.commit()


def job(db, ref):
    return db.execute("SELECT status, tries FROM media_jobs WHERE ref=?", (ref,)).fetchone()


def boom(*_):
    raise RuntimeError("falhou")


def test_youtube_job_becomes_chunks(db, tmp_path):
    add_job(db, "youtube", "https://youtu.be/x", 5)
    segs = [Segment(0, 30, "a"), Segment(30, 65, "b"), Segment(65, 90, "c")]
    n = process_jobs(db, 10, download=lambda u, d: tmp_path / "x.m4a", transcribe=lambda p: segs, fetch=None, out_dir=tmp_path)
    assert n == 1
    rows = db.execute("SELECT text, t_start, source_id, date_utc FROM chunks WHERE source_kind='transcricao' ORDER BY t_start").fetchall()
    assert [tuple(r) for r in rows] == [
        ("a b", 0.0, "https://youtu.be/x", "2026-01-05T10:00:00+00:00"),
        ("c", 65.0, "https://youtu.be/x", "2026-01-05T10:00:00+00:00"),
    ]
    assert tuple(job(db, "https://youtu.be/x")) == ("transcrito", 0)


def test_audio_job_skips_download(db, tmp_path):
    add_job(db, "audio", str(tmp_path / "a.ogg"), 6)
    n = process_jobs(db, 10, download=boom, transcribe=lambda p: [Segment(0, 5, "oi")], fetch=None, out_dir=tmp_path)
    assert n == 1


def test_link_job(db, tmp_path):
    add_job(db, "link", "https://x.com/a", 7)
    n = process_jobs(db, 10, download=None, transcribe=None, fetch=lambda u: "texto do artigo", out_dir=tmp_path)
    assert n == 1
    row = db.execute("SELECT text, source_kind FROM chunks").fetchone()
    assert tuple(row) == ("texto do artigo", "link")


def test_failure_counts_tries_and_stops_at_3(db, tmp_path):
    add_job(db, "youtube", "https://youtu.be/y", 5)
    for expected in [("pendente", 1), ("pendente", 2), ("erro", 3), ("erro", 3)]:
        assert process_jobs(db, 10, download=boom, transcribe=None, fetch=None, out_dir=tmp_path) == 0
        assert tuple(job(db, "https://youtu.be/y")) == expected
    assert db.execute("SELECT error FROM media_jobs").fetchone()[0] == "falhou"


def test_link_without_text_is_failure(db, tmp_path):
    add_job(db, "link", "https://x.com/b", 7)
    process_jobs(db, 10, download=None, transcribe=None, fetch=lambda u: None, out_dir=tmp_path)
    assert tuple(job(db, "https://x.com/b")) == ("pendente", 1)


def test_newest_message_first_and_limit(db, tmp_path):
    add_job(db, "link", "old", 1)
    add_job(db, "link", "new", 9)
    seen = []
    def fetch(u):
        seen.append(u)
        return "t"
    assert process_jobs(db, 1, download=None, transcribe=None, fetch=fetch, out_dir=tmp_path) == 1
    assert seen == ["new"]


def test_youtube_opts_skip_playlist_live_and_big_files(tmp_path, monkeypatch):
    seen = {}

    class FakeYDL:  # yt_dlp falso: nada é baixado
        def __init__(self, opts):
            seen.update(opts)

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def extract_info(self, url, download):
            return {"id": "abc"}

    fake = types.ModuleType("yt_dlp")
    fake.YoutubeDL = FakeYDL
    fake.utils = types.SimpleNamespace(match_filter_func=lambda expr: ("filtro", expr))
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    assert download_audio("https://youtu.be/abc?list=PL1", tmp_path) == tmp_path / "abc.m4a"
    assert seen["noplaylist"] is True
    assert seen["match_filter"] == ("filtro", "!is_live")
    assert seen["max_filesize"] == 500 * 1024 * 1024


@pytest.fixture
def fake_trafilatura(monkeypatch):
    """Extração falsa; o host público resolve para um IP público e a rede é o respx."""
    fake = types.ModuleType("trafilatura")
    fake.extract = lambda html, url=None: "texto"
    monkeypatch.setitem(sys.modules, "trafilatura", fake)
    import socket
    ips = {"example.com": "93.184.216.34", "interno.example.com": "192.168.0.9"}
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, *a, **k: [(None, None, None, None, (ips[host], 0))] if host in ips else (_ for _ in ()).throw(OSError()))
    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.mark.parametrize("url", ["http://127.0.0.1:8000/x", "http://192.168.0.1/", "http://localhost/",
                                 "http://169.254.169.254/", "http://[::1]/", "file:///etc/passwd"])
def test_link_to_local_network_is_refused(url, fake_trafilatura):
    assert fetch_text(url) is None
    assert not fake_trafilatura.calls


def test_public_link_is_fetched(fake_trafilatura):
    fake_trafilatura.get("https://example.com/artigo").respond(200, text="<html>")
    assert fetch_text("https://example.com/artigo") == "texto"


def test_host_that_resolves_to_local_ip_or_unknown_is_refused(fake_trafilatura):
    assert fetch_text("https://interno.example.com/") is None
    assert fetch_text("https://nao-existe.example/") is None
    assert not fake_trafilatura.calls


def test_redirect_to_local_network_is_refused_and_public_redirect_followed(fake_trafilatura):
    fake_trafilatura.get("https://example.com/a").respond(302, headers={"location": "http://127.0.0.1:8000/api/overview"})
    assert fetch_text("https://example.com/a") is None
    fake_trafilatura.get("https://example.com/b").respond(301, headers={"location": "/c"})
    fake_trafilatura.get("https://example.com/c").respond(200, text="<html>")
    assert fetch_text("https://example.com/b") == "texto"
    fake_trafilatura.get("https://example.com/erro").respond(500)
    assert fetch_text("https://example.com/erro") is None

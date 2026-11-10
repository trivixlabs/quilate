import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from quilate.media.links import fetch_text
from quilate.media.transcribe import Segment
from quilate.media.transcribe import transcribe as whisper
from quilate.media.youtube import download_audio

MAX_TRIES = 3
BLOCK_SECONDS = 60


def group_segments(segments: list[Segment]) -> list[tuple[float, str]]:
    """Blocos de até 60 s: o segmento entra no bloco se start < início do bloco + 60."""
    blocks: list[tuple[float, list[str]]] = []
    for s in segments:
        if blocks and s.start < blocks[-1][0] + BLOCK_SECONDS:
            blocks[-1][1].append(s.text)
        else:
            blocks.append((float(s.start), [s.text]))
    return [(start, " ".join(texts)) for start, texts in blocks]


def _save(conn, kind: str, ref: str, rows: list[tuple[float | None, str]], date_utc: str) -> None:
    conn.execute("DELETE FROM chunks WHERE source_kind=? AND source_id=?", (kind, ref))
    conn.executemany(
        "INSERT INTO chunks (source_kind, source_id, text, t_start, date_utc) VALUES (?,?,?,?,?)",
        [(kind, ref, text, t, date_utc) for t, text in rows],
    )


def process_jobs(conn: sqlite3.Connection, limit: int, download=download_audio, transcribe=whisper,
                 fetch=fetch_text, *, out_dir: Path) -> int:
    """`out_dir`: pasta do áudio baixado do YouTube, dentro de settings.media_dir."""
    jobs = conn.execute(
        "SELECT j.id, j.kind, j.ref, j.tries, m.date_utc FROM media_jobs j "
        "LEFT JOIN messages m ON m.msg_id = j.msg_id WHERE j.status IN ('pendente','baixado') "
        "ORDER BY j.msg_id DESC LIMIT ?", (limit,)
    ).fetchall()
    done = 0
    for job_id, kind, ref, tries, date_utc in jobs:
        date_utc = date_utc or datetime.now(UTC).isoformat()
        try:
            if kind == "link":
                text = fetch(ref)
                if not text:
                    raise RuntimeError("link sem texto extraível")
                _save(conn, "link", ref, [(None, text)], date_utc)
            else:
                path = Path(ref) if kind == "audio" else download(ref, out_dir)
                rows = group_segments(transcribe(path))  # antes de escrever: o Whisper não segura a trava do banco
                conn.execute("UPDATE media_jobs SET status='baixado', path=? WHERE id=?", (str(path), job_id))
                _save(conn, "transcricao", ref, rows, date_utc)
            conn.execute("UPDATE media_jobs SET status='transcrito', error=NULL WHERE id=?", (job_id,))
            done += 1
        except Exception as exc:
            conn.rollback()
            tries += 1
            conn.execute("UPDATE media_jobs SET status=?, tries=?, error=? WHERE id=?",
                         ("erro" if tries >= MAX_TRIES else "pendente", tries, str(exc), job_id))
        conn.commit()
    return done

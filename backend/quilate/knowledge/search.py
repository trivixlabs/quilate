import re
from dataclasses import dataclass
from datetime import UTC, datetime

import sqlite_vec


@dataclass
class Hit:
    chunk_id: int
    source_kind: str
    source_id: str
    text: str
    score: float
    date_utc: str
    analyst: bool = False  # preenchido pelo veredito para chunk de mensagem do analista


def rrf_merge(lists: list[list[int]], k: int = 60) -> list[tuple[int, float]]:
    scores: dict[int, float] = {}
    for ids in lists:
        for rank, i in enumerate(ids, start=1):
            scores[i] = scores.get(i, 0.0) + 1 / (k + rank)
    return sorted(scores.items(), key=lambda p: p[1], reverse=True)


def _fts_query(q: str) -> str:
    # cada termo vira string entre aspas: pontuação e operadores (OR, -, *) deixam de ser sintaxe do FTS5
    return " OR ".join(f'"{t}"' for t in re.findall(r"\w+", q))


def search(conn, embedder, query: str, k: int = 20, since_utc: datetime | None = None, pool: int = 50,
           query_vec: list[float] | None = None) -> list[Hit]:
    """`query_vec`: vetor da consulta já calculado (fora do loop do asyncio). Sem ele, o embedder calcula aqui."""
    since = since_utc.astimezone(UTC).isoformat() if since_utc else None
    fts_ids: list[int] = []
    match = _fts_query(query)
    if match:
        sql = "SELECT c.id FROM chunks_fts f JOIN chunks c ON c.id = f.rowid WHERE chunks_fts MATCH ?"
        args: list = [match]
        if since:
            sql += " AND c.date_utc >= ?"
            args.append(since)
        fts_ids = [r[0] for r in conn.execute(sql + " ORDER BY bm25(chunks_fts) LIMIT ?", [*args, pool])]
    vec = sqlite_vec.serialize_float32(query_vec if query_vec is not None else embedder.encode([query])[0])
    sql = "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? AND k = ?"
    args = [vec, pool]
    if since:
        sql += " AND rowid IN (SELECT id FROM chunks WHERE date_utc >= ?)"
        args.append(since)
    vec_ids = [r[0] for r in conn.execute(sql + " ORDER BY distance", args)]
    merged = rrf_merge([fts_ids, vec_ids])[:k]
    rows = {
        r["id"]: r
        for r in conn.execute(
            f"SELECT * FROM chunks WHERE id IN ({','.join('?' * len(merged))})", [i for i, _ in merged]
        )
    }
    return [
        Hit(i, rows[i]["source_kind"], rows[i]["source_id"], rows[i]["text"], s, rows[i]["date_utc"])
        for i, s in merged
        if i in rows
    ]

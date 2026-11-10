import sqlite_vec


def index_pending(conn, embedder, batch: int = 64) -> int:
    """Cria/atualiza chunks de mensagens e grava o vetor de todo chunk sem vetor. Devolve quantos vetores gravou."""
    # mensagem editada: atualiza o texto do chunk e descarta o vetor velho
    stale = conn.execute(
        "SELECT c.id, m.text FROM chunks c JOIN messages m ON c.source_kind='mensagem' AND c.source_id = CAST(m.msg_id AS TEXT) "
        "WHERE m.text IS NOT NULL AND m.text != '' AND c.text != m.text"
    ).fetchall()
    for cid, text in stale:
        conn.execute("UPDATE chunks SET text=? WHERE id=?", (text, cid))
        conn.execute("DELETE FROM chunks_vec WHERE rowid=?", (cid,))
    # mensagem editada para vazio: o chunk (e o vetor, via trigger) sai
    conn.execute(
        "DELETE FROM chunks WHERE source_kind='mensagem' AND source_id IN "
        "(SELECT CAST(msg_id AS TEXT) FROM messages WHERE text IS NULL OR text = '')"
    )
    conn.execute(
        "INSERT INTO chunks (source_kind, source_id, text, date_utc) "
        "SELECT 'mensagem', CAST(m.msg_id AS TEXT), m.text, m.date_utc FROM messages m "
        "WHERE m.text IS NOT NULL AND m.text != '' AND NOT EXISTS "
        "(SELECT 1 FROM chunks c WHERE c.source_kind='mensagem' AND c.source_id = CAST(m.msg_id AS TEXT))"
    )
    # rede de segurança (bancos antigos, sem o trigger)
    conn.execute("DELETE FROM chunks_vec WHERE rowid NOT IN (SELECT id FROM chunks)")
    conn.commit()  # embeddings levam tempo: a trava de escrita não fica presa durante o cálculo
    pending = conn.execute("SELECT id, text FROM chunks WHERE id NOT IN (SELECT rowid FROM chunks_vec) ORDER BY id").fetchall()
    for i in range(0, len(pending), batch):
        part = pending[i : i + batch]
        for (cid, _), vec in zip(part, embedder.encode([t for _, t in part]), strict=True):
            conn.execute("INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)", (cid, sqlite_vec.serialize_float32(vec)))
        conn.commit()
    return len(pending)

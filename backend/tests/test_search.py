from datetime import UTC, datetime

from quilate.knowledge.index import index_pending
from quilate.knowledge.search import rrf_merge, search


class FakeEmbedder:
    def __init__(self, table):
        self.table = table
        self.calls = 0

    def encode(self, texts):
        self.calls += len(texts)
        return [list(self.table.get(t, [0.0, 0.0, 1.0])) + [0.0] * (768 - len(self.table.get(t, [0, 0, 1]))) for t in texts]


def seed_chunks(db, emb, texts, date="2026-01-01T00:00:00+00:00"):
    for i, t in enumerate(texts, start=1):
        db.execute("INSERT INTO messages (msg_id, date_utc, text) VALUES (?,?,?)", (i, date, t))
    index_pending(db, emb)


def test_rrf_order():
    assert [i for i, _ in rrf_merge([[1, 2, 3], [3, 1]])][:2] == [1, 3]


def test_hybrid_finds_word_and_meaning(db):
    emb = FakeEmbedder({"realizar lucro": [1, 0], "vender parte": [0.99, 0.1], "suporte do BTC": [0, 1]})
    seed_chunks(db, emb, ["vender parte", "suporte do BTC"])
    hits = search(db, emb, "realizar lucro", k=5)
    assert hits[0].text == "vender parte"

def test_fts_leg_alone_finds_word(db):
    # pool=1: o vetor devolve só "vender parte"; "suporte do BTC" só pode vir do FTS
    emb = FakeEmbedder({"suporte": [1, 0], "vender parte": [1, 0], "suporte do BTC": [0, 1]})
    seed_chunks(db, emb, ["vender parte", "suporte do BTC"])
    assert any(h.text == "suporte do BTC" for h in search(db, emb, "suporte", k=5, pool=1))


def test_query_with_punctuation_does_not_break(db):
    emb = FakeEmbedder({"BTC/USDT": [1, 0], "outro": [1, 0], "BTC/USDT perdeu o suporte": [0, 1]})
    seed_chunks(db, emb, ["outro", "BTC/USDT perdeu o suporte"])
    for q in ['-', '"aspas', 'a OR (b', '', '***']:
        search(db, emb, q, k=5, pool=1)
    # pool=1: o vetor devolve só "outro"; o alvo só pode vir do FTS
    assert any(h.text == "BTC/USDT perdeu o suporte" for h in search(db, emb, "BTC/USDT", k=5, pool=1))


def test_since_utc_filters_both_searches(db):
    emb = FakeEmbedder({"q": [1, 0], "velho q": [1, 0], "novo q": [0.9, 0.1]})
    db.execute("INSERT INTO messages (msg_id, date_utc, text) VALUES (1,'2025-01-01T00:00:00+00:00','velho q')")
    db.execute("INSERT INTO messages (msg_id, date_utc, text) VALUES (2,'2026-06-01T00:00:00+00:00','novo q')")
    index_pending(db, emb)
    hits = search(db, emb, "q", k=5, since_utc=datetime(2026, 1, 1, tzinfo=UTC))
    assert [h.text for h in hits] == ["novo q"]


def test_index_pending_idempotent_and_handles_edit(db):
    emb = FakeEmbedder({"a": [1, 0], "b": [0, 1]})
    seed_chunks(db, emb, ["a"])
    assert index_pending(db, emb) == 0
    assert db.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1
    db.execute("UPDATE messages SET text='b' WHERE msg_id=1")
    assert index_pending(db, emb) == 1
    assert db.execute("SELECT text FROM chunks").fetchone()[0] == "b"
    assert db.execute("SELECT count(*) FROM chunks_vec").fetchone()[0] == 1
    assert search(db, emb, "b", k=3)[0].text == "b"


def test_index_pending_skips_empty_and_cleans_orphan_vectors(db):
    emb = FakeEmbedder({})
    db.execute("INSERT INTO messages (msg_id, date_utc, text) VALUES (1,'2026-01-01T00:00:00+00:00','')")
    db.execute("INSERT INTO messages (msg_id, date_utc, text) VALUES (2,'2026-01-01T00:00:00+00:00',NULL)")
    db.execute("INSERT INTO chunks (source_kind, source_id, text, date_utc) VALUES ('link','x','texto','2026-01-01T00:00:00+00:00')")
    index_pending(db, emb)
    assert db.execute("SELECT count(*) FROM chunks").fetchone()[0] == 1
    assert db.execute("SELECT count(*) FROM chunks_vec").fetchone()[0] == 1
    db.execute("DELETE FROM chunks")
    index_pending(db, emb)
    assert db.execute("SELECT count(*) FROM chunks_vec").fetchone()[0] == 0


def test_reused_chunk_id_is_reembedded(db):
    emb = FakeEmbedder({})
    db.execute("INSERT INTO chunks (id, source_kind, source_id, text, date_utc) VALUES (7,'link','x','velho','2026-01-01T00:00:00+00:00')")
    index_pending(db, emb)
    db.execute("DELETE FROM chunks WHERE id=7")
    db.execute("INSERT INTO chunks (id, source_kind, source_id, text, date_utc) VALUES (7,'link','x','novo','2026-01-01T00:00:00+00:00')")
    assert index_pending(db, emb) == 1


def test_orphan_cleanup_is_partial(db):
    import sqlite_vec

    emb = FakeEmbedder({})
    seed_chunks(db, emb, ["a", "b"])
    db.execute("INSERT INTO chunks_vec(rowid, embedding) VALUES (999, ?)", (sqlite_vec.serialize_float32([0.0] * 768),))
    index_pending(db, emb)
    assert sorted(r[0] for r in db.execute("SELECT rowid FROM chunks_vec")) == [1, 2]


def test_message_edited_to_empty_drops_chunk_and_vector(db):
    emb = FakeEmbedder({})
    seed_chunks(db, emb, ["a", "b"])
    db.execute("UPDATE messages SET text='' WHERE msg_id=1")
    index_pending(db, emb)
    assert [r[0] for r in db.execute("SELECT text FROM chunks")] == ["b"]
    assert db.execute("SELECT count(*) FROM chunks_vec").fetchone()[0] == 1

import sqlite3

import pytest

from quilate.db import connect, migrate


def test_migrate_twice_is_safe(tmp_path):
    conn = connect(tmp_path / "t.db")
    migrate(conn)
    migrate(conn)
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_verdicts_are_append_only(db):
    db.execute("INSERT INTO verdicts(day, symbol, trigger, rubric_verdict, final_verdict, signals_json, pros_json, cons_json, main_risk, cited_json, no_analyst, price_usd, price_btc, created_utc) VALUES ('2026-11-04','ARB','diario','Sair','Sair','[]','[]','[]','','[]',0,0.41,0.000004,'x')")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("UPDATE verdicts SET final_verdict='Manter'")
    with pytest.raises(sqlite3.IntegrityError):
        db.execute("DELETE FROM verdicts")


def test_fts_finds_message(db):
    db.execute("INSERT INTO messages(msg_id, topic_id, is_analyst, date_utc, text) VALUES (1, 101, 1, '2026-11-04T11:42:00Z', 'BTC segura o suporte')")
    assert db.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'suporte'").fetchall()
    db.execute("UPDATE messages SET text='nada' WHERE msg_id=1")
    assert not db.execute("SELECT rowid FROM messages_fts WHERE messages_fts MATCH 'suporte'").fetchall()


def test_vec_table_exists(db):
    db.execute("SELECT count(*) FROM chunks_vec").fetchone()

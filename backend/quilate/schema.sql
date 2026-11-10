CREATE TABLE IF NOT EXISTS messages (
  msg_id INTEGER PRIMARY KEY, topic_id INTEGER, author_id INTEGER, author_username TEXT,
  is_analyst INTEGER NOT NULL DEFAULT 0, date_utc TEXT NOT NULL, text TEXT,
  reply_to INTEGER, edited_utc TEXT, media_kind TEXT, media_path TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, content='messages', content_rowid='msg_id');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, text) VALUES (new.msg_id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.msg_id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, text) VALUES ('delete', old.msg_id, old.text);
  INSERT INTO messages_fts(rowid, text) VALUES (new.msg_id, new.text);
END;

CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY,
  source_kind TEXT NOT NULL CHECK (source_kind IN ('mensagem','transcricao','link')),
  source_id TEXT NOT NULL, text TEXT NOT NULL, t_start REAL, date_utc TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(text, content='chunks', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
  INSERT INTO chunks_fts(chunks_fts, rowid, text) VALUES ('delete', old.id, old.text);
  INSERT INTO chunks_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(embedding float[768]);
CREATE TRIGGER IF NOT EXISTS chunks_vec_ad AFTER DELETE ON chunks BEGIN
  DELETE FROM chunks_vec WHERE rowid = old.id;
END;

CREATE TABLE IF NOT EXISTS media_jobs (
  id INTEGER PRIMARY KEY,
  kind TEXT NOT NULL CHECK (kind IN ('youtube','audio','link')),
  ref TEXT NOT NULL UNIQUE, msg_id INTEGER,
  status TEXT NOT NULL DEFAULT 'pendente' CHECK (status IN ('pendente','baixado','transcrito','erro')),
  tries INTEGER NOT NULL DEFAULT 0, error TEXT, path TEXT
);

CREATE TABLE IF NOT EXISTS mentions (
  id INTEGER PRIMARY KEY, msg_id INTEGER NOT NULL, chunk_id INTEGER, symbol TEXT NOT NULL,
  is_analyst INTEGER NOT NULL DEFAULT 0,
  stance TEXT CHECK (stance IN ('comprar','manter','realizar','sair')),
  price_level REAL, polarity INTEGER, date_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
  exchange TEXT NOT NULL, symbol TEXT NOT NULL, wallet TEXT NOT NULL, qty REAL NOT NULL,
  updated_utc TEXT NOT NULL, stale INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (exchange, symbol, wallet)
);

CREATE TABLE IF NOT EXISTS trades (
  exchange TEXT NOT NULL, trade_id TEXT NOT NULL, symbol TEXT NOT NULL,
  side TEXT NOT NULL CHECK (side IN ('buy','sell')),
  qty REAL NOT NULL, price_usd REAL NOT NULL, fee_usd REAL NOT NULL DEFAULT 0, ts_utc TEXT NOT NULL,
  source TEXT NOT NULL CHECK (source IN ('api','csv','manual')),
  UNIQUE (exchange, trade_id, source)
);

CREATE TABLE IF NOT EXISTS cost_overrides (
  symbol TEXT PRIMARY KEY, avg_cost_usd REAL NOT NULL, qty REAL, note TEXT, updated_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS candles (
  venue TEXT NOT NULL, symbol TEXT NOT NULL, quote TEXT NOT NULL, day TEXT NOT NULL,
  open REAL, high REAL, low REAL, close REAL, volume_quote REAL,
  PRIMARY KEY (venue, symbol, quote, day)
);

CREATE TABLE IF NOT EXISTS snapshots (
  day TEXT NOT NULL, key TEXT NOT NULL, value_json TEXT NOT NULL, PRIMARY KEY (day, key)
);

CREATE TABLE IF NOT EXISTS playbook_versions (
  id INTEGER PRIMARY KEY, created_utc TEXT NOT NULL, model TEXT, markdown TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'rascunho' CHECK (status IN ('rascunho','aprovado')),
  parent_id INTEGER
);
CREATE TABLE IF NOT EXISTS playbook_rules (
  id INTEGER PRIMARY KEY, version_id INTEGER NOT NULL REFERENCES playbook_versions(id),
  category TEXT, text TEXT NOT NULL, source_ids_json TEXT NOT NULL DEFAULT '[]',
  approved INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS verdicts (
  id INTEGER PRIMARY KEY, day TEXT NOT NULL, symbol TEXT NOT NULL, trigger TEXT NOT NULL,
  rubric_verdict TEXT NOT NULL, ai_verdict TEXT, final_verdict TEXT NOT NULL, confidence REAL,
  signals_json TEXT NOT NULL, pros_json TEXT NOT NULL, cons_json TEXT NOT NULL,
  main_risk TEXT NOT NULL, cited_json TEXT NOT NULL, no_analyst INTEGER NOT NULL DEFAULT 0,
  flag TEXT, price_usd REAL NOT NULL, price_btc REAL NOT NULL, created_utc TEXT NOT NULL
);
CREATE TRIGGER IF NOT EXISTS verdicts_no_update BEFORE UPDATE ON verdicts BEGIN
  SELECT RAISE(ABORT, 'vereditos sao somente insercao');
END;
CREATE TRIGGER IF NOT EXISTS verdicts_no_delete BEFORE DELETE ON verdicts BEGIN
  SELECT RAISE(ABORT, 'vereditos sao somente insercao');
END;

CREATE TABLE IF NOT EXISTS api_costs (
  id INTEGER PRIMARY KEY, ts_utc TEXT NOT NULL, model TEXT NOT NULL, purpose TEXT NOT NULL,
  one_time INTEGER NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,
  output_tokens INTEGER NOT NULL DEFAULT 0, cache_write_tokens INTEGER NOT NULL DEFAULT 0,
  cache_read_tokens INTEGER NOT NULL DEFAULT 0, usd REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts_sent (
  day TEXT NOT NULL, key TEXT NOT NULL, PRIMARY KEY (day, key)
);

CREATE TABLE IF NOT EXISTS mentions_done (
  kind TEXT NOT NULL CHECK (kind IN ('analista','grupo','trecho')), ref TEXT NOT NULL, PRIMARY KEY (kind, ref)
);

-- regras extraídas por parte do manual inicial: se a consolidação falhar, a nova rodada não paga os meses de novo
CREATE TABLE IF NOT EXISTS playbook_drafts (
  part_hash TEXT PRIMARY KEY, rules_json TEXT NOT NULL, created_utc TEXT NOT NULL
);

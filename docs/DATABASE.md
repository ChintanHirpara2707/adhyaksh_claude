# Database — SQLite schema reference

SQLite schema (`adhyaksh/db.py`, `SCHEMA_V1`), every table and column:

- `profile(id INTEGER PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL)` — single-operator name profile.
- `settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)` — all settings key/value.
- `conversations(id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)` — conversation list.
- `messages(id INTEGER PRIMARY KEY, conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, intent TEXT, confidence REAL, latency_ms REAL, created_at TEXT NOT NULL)` — chat history. Index `idx_messages_conv` on conversation_id.
- `memory_facts(id INTEGER PRIMARY KEY, fact TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)` — remembered facts.
- `documents(id INTEGER PRIMARY KEY, filename TEXT NOT NULL, filepath TEXT NOT NULL, pages INTEGER, indexed_at TEXT, status TEXT NOT NULL DEFAULT 'pending')` — indexed documents.
- `doc_chunks(id INTEGER PRIMARY KEY, document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, chunk_index INTEGER NOT NULL, page_or_section TEXT, text TEXT NOT NULL, embedding BLOB NULL, method TEXT NOT NULL DEFAULT 'tfidf')` — document chunks. Index `idx_chunks_doc` on document_id.
- `audit_log(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, user_text TEXT, intent TEXT, action TEXT NOT NULL, target TEXT, level INTEGER NOT NULL, confirmed TEXT NOT NULL DEFAULT 'none', result TEXT NOT NULL)` — append-only audit. Triggers `audit_log_no_update` and `audit_log_no_delete` prevent changes.
- `model_registry(id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, dataset_hash TEXT, trained_at TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 0)` — trained model registry.
- `eval_runs(id INTEGER PRIMARY KEY, model_id INTEGER REFERENCES model_registry(id) ON DELETE CASCADE, accuracy REAL, macro_f1 REAL, per_language_json TEXT, confusion_json TEXT, size_bytes INTEGER, p50_ms REAL, p95_ms REAL, created_at TEXT NOT NULL)` — evaluation results.
- `feedback(id INTEGER PRIMARY KEY, message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE, correct_intent TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL)` — "Wrong intent?" corrections.

`db.py` also provides: `connect()` context manager (WAL journal, foreign_keys=ON), `schema_version()`, `init()` (runs migrations), `execute()`, `executemany()`, `query_all()`, `query_one()`, `get_setting()`, `set_setting()`, `backup()`, `restore()`, `export_bytes()`, `wipe()`, `utcnow()`.

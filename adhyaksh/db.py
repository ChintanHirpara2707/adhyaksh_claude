"""SQLite access. Only this module touches sqlite3 directly.

Usage from the shell:  python -m adhyaksh.db backup [destination]
"""
from __future__ import annotations

import shutil
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

from adhyaksh import config

SCHEMA_V1 = """
CREATE TABLE profile(
  id INTEGER PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE settings(
  key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE conversations(
  id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL);
CREATE TABLE messages(
  id INTEGER PRIMARY KEY,
  conversation_id INTEGER NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT NOT NULL, intent TEXT, confidence REAL,
  latency_ms REAL, created_at TEXT NOT NULL);
CREATE INDEX idx_messages_conv ON messages(conversation_id);
CREATE TABLE memory_facts(
  id INTEGER PRIMARY KEY, fact TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general',
  created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE documents(
  id INTEGER PRIMARY KEY, filename TEXT NOT NULL, filepath TEXT NOT NULL,
  pages INTEGER, indexed_at TEXT, status TEXT NOT NULL DEFAULT 'pending');
CREATE TABLE doc_chunks(
  id INTEGER PRIMARY KEY,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL, page_or_section TEXT, text TEXT NOT NULL,
  embedding BLOB NULL, method TEXT NOT NULL DEFAULT 'tfidf');
CREATE INDEX idx_chunks_doc ON doc_chunks(document_id);
CREATE TABLE audit_log(
  id INTEGER PRIMARY KEY, ts TEXT NOT NULL, user_text TEXT, intent TEXT,
  action TEXT NOT NULL, target TEXT, level INTEGER NOT NULL,
  confirmed TEXT NOT NULL DEFAULT 'none', result TEXT NOT NULL);
CREATE TRIGGER audit_log_no_update BEFORE UPDATE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER audit_log_no_delete BEFORE DELETE ON audit_log
  BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TABLE model_registry(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL,
  dataset_hash TEXT, trained_at TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 0);
CREATE TABLE eval_runs(
  id INTEGER PRIMARY KEY,
  model_id INTEGER NOT NULL REFERENCES model_registry(id) ON DELETE CASCADE,
  accuracy REAL, macro_f1 REAL, per_language_json TEXT, confusion_json TEXT,
  size_bytes INTEGER, p50_ms REAL, p95_ms REAL, created_at TEXT NOT NULL);
CREATE TABLE feedback(
  id INTEGER PRIMARY KEY,
  message_id INTEGER NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
  correct_intent TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL);
"""

MIGRATIONS: list[tuple[int, str]] = [(1, SCHEMA_V1)]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(path: Path | str | None = None) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or config.db_path()), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


@contextmanager
def connect(path: Path | str | None = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def schema_version(path: Path | str | None = None) -> int:
    with connect(path) as conn:
        return int(conn.execute("PRAGMA user_version").fetchone()[0])


def init(path: Path | str | None = None) -> int:
    """Create or upgrade the schema through versioned migrations. Idempotent."""
    with connect(path) as conn:
        current = int(conn.execute("PRAGMA user_version").fetchone()[0])
        for version, sql in MIGRATIONS:
            if version > current:
                conn.executescript(f"BEGIN;\n{sql}\nPRAGMA user_version={version};\nCOMMIT;")
                current = version
    return current


def execute(sql: str, params: Sequence[Any] = (), path: Path | str | None = None) -> int:
    with connect(path) as conn:
        return int(conn.execute(sql, params).lastrowid or 0)


def executemany(sql: str, rows: Sequence[Sequence[Any]], path: Path | str | None = None) -> None:
    with connect(path) as conn:
        conn.executemany(sql, rows)


def query_all(sql: str, params: Sequence[Any] = (), path: Path | str | None = None) -> list[dict]:
    with connect(path) as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def query_one(sql: str, params: Sequence[Any] = (), path: Path | str | None = None) -> dict | None:
    with connect(path) as conn:
        row = conn.execute(sql, params).fetchone()
        return dict(row) if row else None


def get_setting(key: str) -> str | None:
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    return None if row is None else row["value"]


def set_setting(key: str, value: str) -> None:
    execute(
        "INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value, utcnow()),
    )


def backup(dest: Path | str | None = None) -> Path:
    """Copy the live database to dest (default: data/backups/<timestamp>.db)."""
    out = Path(dest) if dest else config.backups_dir() / f"adhyaksh_{time.strftime('%Y%m%d_%H%M%S')}.db"
    src, dst = _connect(), sqlite3.connect(str(out))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    return out


def restore(src_path: Path | str) -> None:
    """Replace the live database content with a backup file."""
    src, dst = sqlite3.connect(str(src_path)), _connect()
    try:
        src.backup(dst)
    finally:
        src.close()
        dst.close()


def export_bytes() -> bytes:
    """A consistent copy of the database for download."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        out = backup(Path(tmp) / "export.db")
        return out.read_bytes()


def wipe() -> None:
    """Delete all local data: database, uploads, logs and backups. Models are kept."""
    import logging
    logging.shutdown()
    for p in config.data_dir().glob("adhyaksh.db*"):
        p.unlink(missing_ok=True)
    for sub in (config.uploads_dir(), config.backups_dir()):
        shutil.rmtree(sub, ignore_errors=True)
    init()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "backup":
        init()
        print(backup(argv[1] if len(argv) > 1 else None))
        return 0
    print("Usage: python -m adhyaksh.db backup [destination]")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

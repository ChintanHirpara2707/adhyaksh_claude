import sqlite3

from adhyaksh import config, db
from tests.helpers import fresh_env

EXPECTED = {"profile", "settings", "conversations", "messages", "memory_facts", "documents",
            "doc_chunks", "audit_log", "model_registry", "eval_runs", "feedback"}


def _tables():
    return {r["name"] for r in db.query_all("SELECT name FROM sqlite_master WHERE type='table'")}


def test_fresh_schema_and_version():
    fresh_env()
    assert EXPECTED <= _tables()
    assert db.schema_version() == db.MIGRATIONS[-1][0]


def test_init_is_idempotent():
    fresh_env()
    db.set_setting("k", "v")
    db.init()
    assert db.get_setting("k") == "v"


def test_wal_and_foreign_keys():
    fresh_env()
    with db.connect() as conn:
        assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1


def test_foreign_key_enforced():
    fresh_env()
    try:
        db.execute("INSERT INTO messages(conversation_id,role,content,created_at) VALUES(999,'user','x','t')")
    except sqlite3.IntegrityError:
        return
    raise AssertionError("foreign key was not enforced")


def test_audit_log_is_append_only():
    fresh_env()
    db.execute("INSERT INTO audit_log(ts,action,level,result) VALUES('t','a',0,'ok')")
    for sql in ("UPDATE audit_log SET result='x'", "DELETE FROM audit_log"):
        try:
            db.execute(sql)
        except sqlite3.DatabaseError:
            continue
        raise AssertionError(f"audit_log allowed: {sql}")
    assert db.query_one("SELECT COUNT(*) AS n FROM audit_log")["n"] == 1


def test_settings_roundtrip_and_defaults():
    fresh_env()
    assert config.get("theme") == ""
    assert config.get_float("confidence_threshold") == 0.60
    assert config.get_bool("cloud_consent") is False
    config.set_value("theme", "dark")
    assert config.get("theme") == "dark"
    try:
        config.get("nonexistent")
    except KeyError:
        return
    raise AssertionError("unknown setting should raise KeyError")


def test_backup_and_restore():
    d = fresh_env()
    db.set_setting("marker", "before")
    out = db.backup(d / "backup.db")
    db.set_setting("marker", "after")
    db.restore(out)
    assert db.get_setting("marker") == "before"


def test_upgrade_existing_database_preserves_data():
    fresh_env()
    db.set_setting("keep", "me")
    db.MIGRATIONS.append((2, "CREATE TABLE extra_t(id INTEGER PRIMARY KEY);"))
    try:
        assert db.init() == 2 and db.schema_version() == 2
        assert db.get_setting("keep") == "me"
        assert "extra_t" in _tables()
    finally:
        db.MIGRATIONS.pop()

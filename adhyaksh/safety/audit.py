"""Append-only audit log. Rows cannot be updated or deleted (enforced by SQLite triggers)."""
from __future__ import annotations

from adhyaksh import db

MAX_TEXT = 1000


def record(
    *,
    user_text: str,
    intent: str,
    action: str,
    target: str,
    level: int,
    confirmed: str,
    result: str,
    ts: str | None = None,
) -> None:
    """Write exactly one audit row. confirmed is one of: none, confirmed, cancelled."""
    db.execute(
        "INSERT INTO audit_log(ts,user_text,intent,action,target,level,confirmed,result) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (ts or db.utcnow(), (user_text or "")[:MAX_TEXT], intent or "", action,
         (target or "")[:MAX_TEXT], level, confirmed, (result or "")[:MAX_TEXT]),
    )


def list_recent(limit: int = 200) -> list[dict]:
    return db.query_all("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))


def count() -> int:
    row = db.query_one("SELECT COUNT(*) AS n FROM audit_log")
    return int(row["n"]) if row else 0

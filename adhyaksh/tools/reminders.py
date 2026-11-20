"""Reminders and simple scheduling stored in SQLite (table reminders, schema v3).

Every change goes through safety.policy.run_guarded: adding or cancelling one reminder is L1, cancelling all is L2
(needs confirmation), listing is L0. Reminders fire while the app is open in a browser: the sidebar checks every
20 seconds and shows a notice (and speaks it when spoken replies are on).
"""
from __future__ import annotations

from datetime import datetime, timedelta

from adhyaksh import db
from adhyaksh.result import E_ACTION_FAILED, E_FILE_NOT_FOUND, Result
from adhyaksh.safety import policy
from adhyaksh.tools import when

FMT = "%Y-%m-%dT%H:%M:%S"


def _ctx(ctx: dict | None) -> dict:
    return {"user_text": (ctx or {}).get("user_text", ""), "intent": (ctx or {}).get("intent", "")}


def _row(r: dict) -> dict:
    due = datetime.strptime(r["due_at"], FMT)
    return {"id": r["id"], "text": r["text"], "due": r["due_at"], "repeat": r["repeat"],
            "when": when.describe(due, r["repeat"]), "status": r["status"]}


def add(text: str, due_iso: str, repeat: str = "none", *, ctx: dict | None = None) -> Result:
    """Store a reminder. due_iso is local time, YYYY-MM-DDTHH:MM:SS."""
    text = " ".join(str(text or "").split())[:200] or "Reminder"
    try:
        due = datetime.strptime(str(due_iso)[:19], FMT)
    except ValueError:
        return Result.failure(E_ACTION_FAILED, "The reminder time is not valid.")
    if repeat not in ("none", "daily"):
        repeat = "none"
    if due < datetime.now() - timedelta(minutes=1) and repeat == "none":
        return Result.failure(E_ACTION_FAILED, "That time has already passed.")

    def go() -> Result:
        rid = db.execute("INSERT INTO reminders(text, due_at, repeat, status, created_at) VALUES(?,?,?,?,?)",
                         (text, due.strftime(FMT), repeat, "pending", db.utcnow()))
        return Result.success({"id": rid, "text": text, "due": due.strftime(FMT), "repeat": repeat, "when": when.describe(due, repeat)})
    return policy.run_guarded("reminder_add", text, go, **_ctx(ctx))


def add_natural(request: str, *, ctx: dict | None = None) -> Result:
    """Add a reminder from a sentence such as 'remind me to call mom at 6 pm'. Fails with a clear message when no
    time is given, so the caller can ask for it."""
    w = when.parse(request)
    if w.due is None:
        return Result.failure(E_ACTION_FAILED, "When should I remind you?", {"need": "when", "text": when.reminder_text(request)})
    return add(when.reminder_text(request), w.due.strftime(FMT), w.repeat, ctx=ctx)


def list_pending(*, ctx: dict | None = None) -> Result:
    def go() -> Result:
        rows = db.query_all("SELECT * FROM reminders WHERE status='pending' ORDER BY due_at")
        return Result.success({"reminders": [_row(r) for r in rows]})
    return policy.run_guarded("reminder_list", "reminders", go, **_ctx(ctx))


def find(query: str) -> list[dict]:
    """Pending reminders whose text contains the words of the query (or the id)."""
    q = str(query or "").strip().casefold()
    rows = db.query_all("SELECT * FROM reminders WHERE status='pending' ORDER BY due_at")
    if q.isdigit():
        return [r for r in rows if r["id"] == int(q)]
    words = [w for w in q.split() if len(w) > 2 and w not in ("the", "about", "reminder", "for", "wala", "valu", "vala")]
    return [r for r in rows if words and all(w in r["text"].casefold() for w in words)] or \
           [r for r in rows if words and any(w in r["text"].casefold() for w in words)]


def cancel(query: str = "", *, all_pending: bool = False, ctx: dict | None = None, token: str | None = None) -> Result:
    """Cancel one reminder (L1) or every pending reminder (L2, needs confirmation)."""
    token = token or (ctx or {}).get("token")
    if all_pending:
        n = len(db.query_all("SELECT id FROM reminders WHERE status='pending'"))
        if not n:
            return Result.failure(E_FILE_NOT_FOUND, "You have no pending reminders.")

        def go_all() -> Result:
            db.execute("UPDATE reminders SET status='cancelled' WHERE status='pending'")
            return Result.success({"cancelled": n})
        return policy.run_guarded("reminder_cancel_all", f"{n} reminders", go_all, token=token, **_ctx(ctx))
    matches = find(query)
    if not matches:
        return Result.failure(E_FILE_NOT_FOUND, "No pending reminder matches that.")
    target = matches[0]

    def go() -> Result:
        db.execute("UPDATE reminders SET status='cancelled' WHERE id=?", (target["id"],))
        return Result.success({"cancelled": 1, "text": target["text"]})
    return policy.run_guarded("reminder_cancel", target["text"], go, **_ctx(ctx))


def due(now: datetime | None = None) -> list[dict]:
    """Reminders that are due now. One-shot ones are marked done; daily ones move to the next day."""
    now = now or datetime.now()
    rows = db.query_all("SELECT * FROM reminders WHERE status='pending' AND due_at<=? ORDER BY due_at", (now.strftime(FMT),))
    fired = []
    for r in rows:
        if r["repeat"] == "daily":
            nxt = datetime.strptime(r["due_at"], FMT)
            while nxt <= now:
                nxt += timedelta(days=1)
            db.execute("UPDATE reminders SET due_at=?, fired_at=? WHERE id=?", (nxt.strftime(FMT), db.utcnow(), r["id"]))
        else:
            db.execute("UPDATE reminders SET status='done', fired_at=? WHERE id=?", (db.utcnow(), r["id"]))
        fired.append({"id": r["id"], "text": r["text"]})
    return fired

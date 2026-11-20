"""Pending-confirmation store for L2 actions (in-process, one operator)."""
from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

TTL_SECONDS = 300.0


@dataclass
class Pending:
    token: str
    action: str
    target: str
    user_text: str
    intent: str
    created_at: float


class ConfirmationStore:
    def __init__(self, ttl: float = TTL_SECONDS, clock: Callable[[], float] = time.monotonic) -> None:
        self._ttl, self._clock = ttl, clock
        self._items: dict[str, Pending] = {}
        self._lock = threading.Lock()

    def _live(self, token: str) -> Pending | None:
        item = self._items.get(token)
        if item and self._clock() - item.created_at > self._ttl:
            del self._items[token]
            return None
        return item

    def create(self, action: str, target: str, user_text: str = "", intent: str = "") -> Pending:
        pending = Pending(secrets.token_urlsafe(8), action, target, user_text, intent, self._clock())
        with self._lock:
            self._items[pending.token] = pending
        return pending

    def peek(self, token: str) -> Pending | None:
        with self._lock:
            return self._live(token)

    def consume(self, token: str, action: str, target: str) -> Pending | None:
        """One-time use. Returns the pending item only if token, action and target all match."""
        with self._lock:
            item = self._live(token)
            if item is None or item.action != action or item.target != target:
                return None
            del self._items[token]
            return item

    def cancel(self, token: str) -> Pending | None:
        with self._lock:
            item = self._live(token)
            if item:
                del self._items[token]
            return item


class DbConfirmationStore(ConfirmationStore):
    """The same store, kept in SQLite with wall-clock expiry, so a pending confirmation survives a restart of the
    background engine (Phase 3). One-time use and the action-and-target match are unchanged."""

    def __init__(self, ttl: float = TTL_SECONDS, clock: Callable[[], float] = time.time) -> None:
        super().__init__(ttl, clock)

    def _db(self, sql: str, params=(), one: bool = False, write: bool = False):
        import sqlite3

        from adhyaksh import db
        for attempt in range(2):
            try:
                if write:
                    return db.execute(sql, params)
                return db.query_one(sql, params) if one else db.query_all(sql, params)
            except sqlite3.OperationalError:
                if attempt:
                    raise
                db.init()  # first use in a fresh data folder: create the tables, then try again

    def _row(self, token: str) -> Pending | None:
        row = self._db("SELECT * FROM pending_confirmations WHERE token=?", (token,), one=True)
        if row is None:
            return None
        if self._clock() - row["created_at"] > self._ttl:
            self._db("DELETE FROM pending_confirmations WHERE token=?", (token,), write=True)
            return None
        return Pending(row["token"], row["action"], row["target"], row["user_text"] or "", row["intent"] or "", row["created_at"])

    def create(self, action: str, target: str, user_text: str = "", intent: str = "") -> Pending:
        pending = Pending(secrets.token_urlsafe(8), action, target, user_text, intent, self._clock())
        with self._lock:
            self._db("DELETE FROM pending_confirmations WHERE created_at < ?", (self._clock() - self._ttl,), write=True)
            self._db("INSERT INTO pending_confirmations(token,action,target,user_text,intent,created_at) VALUES(?,?,?,?,?,?)",
                     (pending.token, action, target, user_text, intent, pending.created_at), write=True)
        return pending

    def peek(self, token: str) -> Pending | None:
        with self._lock:
            return self._row(token)

    def consume(self, token: str, action: str, target: str) -> Pending | None:
        with self._lock:
            item = self._row(token)
            if item is None or item.action != action or item.target != target:
                return None
            self._db("DELETE FROM pending_confirmations WHERE token=?", (token,), write=True)
            return item

    def cancel(self, token: str) -> Pending | None:
        with self._lock:
            item = self._row(token)
            if item:
                self._db("DELETE FROM pending_confirmations WHERE token=?", (token,), write=True)
                self._db("DELETE FROM confirm_replays WHERE token=?", (token,), write=True)
            return item


STORE = DbConfirmationStore()


# ---- replays: what to run again when "yes" arrives after a restart -------------------------------------------------
def save_replay(token: str, conversation_id: int, intent: str, text: str, slots: dict, mode: str, lang: str) -> None:
    import json
    STORE._db("INSERT OR REPLACE INTO confirm_replays(token,conversation_id,intent,text,slots_json,mode,lang,created_at) "
              "VALUES(?,?,?,?,?,?,?,?)", (token, conversation_id, intent, text, json.dumps(slots, default=str), mode, lang,
                                          time.time()), write=True)


def latest_replay(conversation_id: int) -> dict | None:
    """The newest still-valid replay of this conversation whose token is still pending, else None."""
    import json
    rows = STORE._db("SELECT * FROM confirm_replays WHERE conversation_id=? ORDER BY created_at DESC LIMIT 5", (conversation_id,))
    for row in rows or []:
        if STORE.peek(row["token"]) is not None:
            return {**row, "slots": json.loads(row["slots_json"])}
    return None


def drop_replay(token: str) -> None:
    STORE._db("DELETE FROM confirm_replays WHERE token=?", (token,), write=True)

"""Conversation storage and short-term context (last entity, pending questions)."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from adhyaksh import config, db


@dataclass
class Context:
    last_file: str | None = None
    last_app: str | None = None
    pending_slot: dict | None = None      # {"intent", "need", "slots"}
    pending_confirm: dict | None = None   # {"token", "action", "target", "retry": Callable}
    pending_agent_confirm: dict | None = None  # {"token", "action", "target", "text"}
    pending_name: str | None = None
    agent_steps: list | None = None       # steps from the last agent run


_CTX: dict[int, Context] = {}


def get(conversation_id: int) -> Context:
    return _CTX.setdefault(conversation_id, Context())


def new_conversation(title: str = "Chat") -> int:
    return db.execute("INSERT INTO conversations(title,created_at) VALUES(?,?)", (title, db.utcnow()))


def latest_conversation() -> int:
    row = db.query_one("SELECT id FROM conversations ORDER BY id DESC LIMIT 1")
    return row["id"] if row else new_conversation()


def save_message(conversation_id: int, role: str, content: str, intent: str | None = None,
                 confidence: float | None = None, latency_ms: float | None = None) -> int:
    return db.execute("INSERT INTO messages(conversation_id,role,content,intent,confidence,latency_ms,created_at) "
                      "VALUES(?,?,?,?,?,?,?)", (conversation_id, role, content, intent, confidence, latency_ms, db.utcnow()))


def history(conversation_id: int, turns: int | None = None) -> list[dict]:
    """The last N turns (a turn is one user message and one reply); default from settings."""
    n = (turns or int(config.get("conversation_turns"))) * 2
    rows = db.query_all("SELECT * FROM messages WHERE conversation_id=? ORDER BY id DESC LIMIT ?", (conversation_id, n))
    return rows[::-1]

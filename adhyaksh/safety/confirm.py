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


STORE = ConfirmationStore()

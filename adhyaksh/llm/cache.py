"""Small in-memory response cache with expiry, keyed by provider, model and prompt."""
from __future__ import annotations

import hashlib
import time

_STORE: dict[str, tuple[float, str]] = {}
TTL, MAX_ITEMS = 3600.0, 200


def _key(*parts: str) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def get(*parts: str) -> str | None:
    item = _STORE.get(_key(*parts))
    if item and time.time() - item[0] < TTL:
        return item[1]
    return None


def put(value: str, *parts: str) -> None:
    if len(_STORE) >= MAX_ITEMS:
        _STORE.pop(next(iter(_STORE)))
    _STORE[_key(*parts)] = (time.time(), value)


def clear() -> None:
    _STORE.clear()

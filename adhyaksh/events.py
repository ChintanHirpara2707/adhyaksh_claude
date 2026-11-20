"""In-process event bus: the engine, the safety gateway and the voice pipeline publish what is happening; the local
server forwards it to WebSocket clients (the desktop HUD, the Streamlit console).

Events are small dicts with a "type": "state" (idle, listening, thinking, speaking, executing), "reply", "notice"
(watchdog: battery, CPU, disk, reminders), "confirmation". Publishing never blocks and never raises: a slow or
missing listener cannot slow the assistant down. Event text never contains keys or file contents beyond what the
reply itself shows.
"""
from __future__ import annotations

import queue
import threading
import time

STATES = ("idle", "listening", "thinking", "speaking", "executing")
_MAX_QUEUE = 200
_subs: list[queue.Queue] = []
_lock = threading.Lock()
_state = {"state": "idle", "since": time.time(), "detail": ""}


def subscribe() -> queue.Queue:
    q: queue.Queue = queue.Queue(maxsize=_MAX_QUEUE)
    with _lock:
        _subs.append(q)
    return q


def unsubscribe(q: queue.Queue) -> None:
    with _lock:
        if q in _subs:
            _subs.remove(q)


def publish(kind: str, **data) -> None:
    event = {"type": kind, "ts": round(time.time(), 3), **data}
    with _lock:
        subs = list(_subs)
    for q in subs:
        try:
            q.put_nowait(event)
        except queue.Full:  # a listener that stopped reading loses its oldest events, never blocks us
            try:
                q.get_nowait()
                q.put_nowait(event)
            except (queue.Empty, queue.Full):
                pass


def set_state(state: str, detail: str = "") -> None:
    if state not in STATES:
        return
    if state == _state["state"] and detail == _state["detail"]:
        return
    _state.update(state=state, since=time.time(), detail=detail)
    publish("state", state=state, detail=detail)


def current_state() -> dict:
    return dict(_state)


def reset() -> None:
    """Tests: drop all listeners and go back to idle."""
    with _lock:
        _subs.clear()
    _state.update(state="idle", since=time.time(), detail="")

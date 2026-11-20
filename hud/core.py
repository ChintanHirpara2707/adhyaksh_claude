"""The HUD's logic, without any window: what to show for each event, how the ring looks in each state, how long to
wait before reconnecting. Kept apart from the tkinter code so it can be tested without a screen."""
from __future__ import annotations

import time
from dataclasses import dataclass, field

# Calm colours on a dark disc; one hue per state, so the state is readable from the corner of the eye.
RING = {
    "idle": {"color": "#3a6b7a", "speed": 0.0, "width": 3, "label": "Ready"},
    "listening": {"color": "#38d6ff", "speed": 0.0, "width": 5, "label": "Listening", "pulse": True},
    "thinking": {"color": "#f2b544", "speed": 6.0, "width": 4, "label": "Thinking"},
    "speaking": {"color": "#5ee08a", "speed": 0.0, "width": 5, "label": "Speaking", "pulse": True},
    "executing": {"color": "#6b8cff", "speed": 12.0, "width": 5, "label": "Working"},
    "offline": {"color": "#7a7a7a", "speed": 0.0, "width": 2, "label": "Engine offline"},
}
CAPTION_SECONDS = {"reply": 8.0, "notice": 15.0, "error": 10.0}
MAX_CAPTION = 140


def short(text: str, limit: int = MAX_CAPTION) -> str:
    """One line for the caption: first line, at most `limit` characters, cut at a word."""
    line = " ".join(str(text or "").split("\n")[0].split())
    if len(line) <= limit:
        return line
    cut = line[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "..."


@dataclass
class HudModel:
    state: str = "offline"
    caption: str = ""
    caption_until: float = 0.0
    caption_kind: str = ""
    notices: list[str] = field(default_factory=list)
    connected: bool = False

    def apply(self, event: dict, now: float | None = None) -> None:
        now = time.time() if now is None else now
        kind = event.get("type")
        if kind == "state" and event.get("state") in RING:
            self.state = event["state"]
        elif kind == "reply" and event.get("text"):
            self._show("reply", event["text"], now)
        elif kind == "notice" and event.get("text"):
            self.notices = (self.notices + [event["text"]])[-5:]
            self._show("notice", event["text"], now)

    def set_connected(self, up: bool, now: float | None = None) -> None:
        self.connected = up
        if not up:
            self.state = "offline"
        elif self.state == "offline":
            self.state = "idle"

    def error(self, text: str, now: float | None = None) -> None:
        self._show("error", text, time.time() if now is None else now)

    def _show(self, kind: str, text: str, now: float) -> None:
        if kind == "reply" and self.caption_kind == "notice" and now < self.caption_until:
            return  # a notice (battery, reminder) is not overwritten by a reply while it is still showing
        self.caption, self.caption_kind = short(text), kind
        self.caption_until = now + CAPTION_SECONDS[kind]

    def visible_caption(self, now: float | None = None) -> str:
        now = time.time() if now is None else now
        return self.caption if now < self.caption_until else ""

    def ring(self) -> dict:
        return RING.get(self.state, RING["idle"])


def backoff(attempt: int) -> float:
    """Seconds to wait before reconnect attempt n: 1, 2, 4, 8, then every 15 s."""
    return min(15.0, 2.0 ** max(0, attempt))

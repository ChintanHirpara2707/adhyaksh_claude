"""Phase 3c: the desktop HUD. Its logic is tested without a window; its event link is tested against the real
engine running in this process on a free loopback port (no window is opened, nothing leaves the PC)."""
import queue
import socket
import threading
import time

import pytest

from adhyaksh import config, events, server
from hud import core
from tests.helpers import fresh_env


# ---- logic ------------------------------------------------------------------------------------------------------------
def test_every_engine_state_has_a_distinct_ring():
    assert set(events.STATES) <= set(core.RING)
    colours = [core.RING[s]["color"] for s in events.STATES]
    assert len(set(colours)) == len(colours)


def test_events_drive_state_caption_and_notices():
    m = core.HudModel()
    m.set_connected(True)
    assert m.state == "idle"
    m.apply({"type": "state", "state": "thinking"}, now=0)
    assert m.state == "thinking" and m.ring()["speed"] > 0
    m.apply({"type": "reply", "text": "Opened notepad.\nmore lines"}, now=0)
    assert m.visible_caption(now=1) == "Opened notepad." and m.visible_caption(now=100) == ""
    m.apply({"type": "state", "state": "sideways"}, now=0)
    assert m.state == "thinking"  # unknown states are ignored


def test_a_notice_is_not_overwritten_by_a_reply_while_showing():
    m = core.HudModel()
    m.apply({"type": "notice", "kind": "battery", "text": "Battery is at 12 percent. Plug in the charger."}, now=0)
    m.apply({"type": "reply", "text": "Opened notepad."}, now=2)
    assert m.visible_caption(now=3).startswith("Battery") and m.notices == ["Battery is at 12 percent. Plug in the charger."]
    m.apply({"type": "reply", "text": "Opened paint."}, now=20)
    assert m.visible_caption(now=21) == "Opened paint."


def test_offline_and_back():
    m = core.HudModel()
    m.set_connected(False)
    assert m.state == "offline" and m.ring()["label"] == "Engine offline"
    m.set_connected(True)
    assert m.state == "idle"


def test_captions_are_short_and_cut_at_a_word():
    long = "word " * 60
    s = core.short(long)
    assert len(s) <= core.MAX_CAPTION + 3 and s.endswith("...") and not s.endswith(" ...")


def test_reconnect_backoff():
    assert [core.backoff(i) for i in range(6)] == [1.0, 2.0, 4.0, 8.0, 15.0, 15.0]


def test_hud_has_no_emoji_and_needs_no_new_package():
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent / "hud"
    allowed = {"ctypes", "json", "queue", "threading", "time", "tkinter", "dataclasses", "__future__", "hud", "adhyaksh",
               "websockets", "requests"}
    for f in root.glob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        mods = {(n.module or "").split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        mods |= {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert mods <= allowed, (f.name, mods - allowed)


# ---- the event link against the real engine ---------------------------------------------------------------------------------
@pytest.fixture
def engine_on_loopback():
    import uvicorn
    fresh_env()
    events.reset()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    config.set_value("server_port", port)
    srv = uvicorn.Server(uvicorn.Config(server.create_app(), host="127.0.0.1", port=port, log_level="error"))
    t = threading.Thread(target=srv.run, daemon=True)
    t.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield port
    srv.should_exit = True
    t.join(timeout=5)
    events.reset()


def test_hud_link_receives_engine_events_and_sends_commands(engine_on_loopback):
    from hud.app import EngineLink
    inbox: queue.Queue = queue.Queue()
    link = EngineLink(inbox)
    threading.Thread(target=link.listen, daemon=True).start()
    first = inbox.get(timeout=10)
    assert first == ("connected", True)
    assert inbox.get(timeout=5)[1]["type"] == "state"
    reply = link.post("/v1/message", {"text": "what is 2 + 3"})
    assert "5" in reply["reply"]
    seen = []
    deadline = time.time() + 10
    while time.time() < deadline and not any(e.get("type") == "reply" for e in seen):
        kind, data = inbox.get(timeout=5)
        if kind == "event":
            seen.append(data)
    assert any(e.get("type") == "reply" and "5" in e["text"] for e in seen)
    assert link.get("/v1/voice")["running"] is False
    link.stop()


def test_hud_link_with_a_wrong_token_never_connects(engine_on_loopback):
    from hud.app import EngineLink
    inbox: queue.Queue = queue.Queue()
    link = EngineLink(inbox)
    link.token = "wrong"
    threading.Thread(target=link.listen, daemon=True).start()
    kinds = []
    deadline = time.time() + 6
    while time.time() < deadline:
        try:
            kinds.append(inbox.get(timeout=1))
        except queue.Empty:
            pass
    link.stop()
    assert ("connected", False) in kinds and ("connected", True) not in kinds  # never shown as connected
    assert not any(k == "event" for k, _ in kinds)

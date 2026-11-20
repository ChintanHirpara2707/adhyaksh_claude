"""Phase 4b: the Voice page. Offline: no engine, no microphone, no model. The browser voice component is replaced
by a stub that records what the page asked it to do."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adhyaksh import client, events
from adhyaksh.chat import context, identity
from adhyaksh.result import Result
from adhyaksh.services import voice as vsvc
from adhyaksh.ui import components as ui
from tests.helpers import fresh_env

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "voice.py")


@pytest.fixture
def page(monkeypatch):
    fresh_env()
    events.reset()
    identity.save_name("Tester")
    calls = []

    def fake_voice_input(**kw):
        calls.append(kw)
        return None
    monkeypatch.setattr(vsvc, "voice_input", fake_voice_input)
    monkeypatch.setattr(client, "available", lambda: False)
    return calls


def _run(at=None):
    at = at or AppTest.from_file(PAGE, default_timeout=60)
    return at.run()


def test_orb_has_a_look_and_label_for_every_state():
    for s in events.STATES:
        h = ui.orb_html(s, "<b>detail</b>")
        assert ui.ORB[s][1] in h and ui.ORB[s][0] in h
        assert "<b>" not in h and "<script" not in h
    assert "Ready" in ui.orb_html("nonsense")


def test_state_comes_from_the_event_bus_without_the_engine(monkeypatch):
    fresh_env()
    events.reset()
    monkeypatch.setattr(client, "available", lambda: False)
    events.set_state("thinking", "open notepad")
    assert vsvc.state() == {"state": "thinking", "detail": "open notepad"}
    events.reset()
    assert vsvc.state()["state"] == "idle"


def test_state_comes_from_the_engine_when_it_runs(monkeypatch):
    fresh_env()
    events.reset()
    monkeypatch.setattr(client, "available", lambda: True)
    monkeypatch.setattr(client, "state", lambda: {"state": "speaking", "detail": "", "since": 0})
    assert vsvc.state()["state"] == "speaking"
    monkeypatch.setattr(client, "state", lambda: None)  # engine stopped answering: fall back to the local bus
    assert vsvc.state()["state"] == "idle"


def test_page_renders_orb_transcript_and_stop(page):
    cid = context.new_conversation()
    context.save_message(cid, "user", "what time is it")
    context.save_message(cid, "assistant", "It is ten o'clock.")
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.session_state["cid"] = cid
    at.run()
    assert not at.exception
    assert any("adhy-orb" in h.proto.body for h in at.get("html"))
    assert any("ten o'clock" in m.value for m in at.markdown)
    assert page, "the browser voice control (with its own stop button) is shown"


def test_new_reply_is_spoken_once(page):
    cid = context.new_conversation()
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.session_state["cid"] = cid
    at.run()
    context.save_message(cid, "user", "hello")
    context.save_message(cid, "assistant", "Hello, Tester.")
    at.run()
    assert page[-1]["speak_text"] == "Hello, Tester."
    at.run()
    assert page[-1]["speak_text"] == ""


def test_heard_text_goes_through_the_engine(page, monkeypatch):
    sent = []
    monkeypatch.setattr(vsvc, "voice_input", lambda **kw: {"text": "what is 12 * 7", "nonce": "n1"})
    monkeypatch.setattr(vsvc, "handle_message", lambda text, cid, voice=False, mode="cowork": sent.append((text, voice)) or Result.success({}))
    at = _run()
    assert not at.exception and sent == [("what is 12 * 7", True)]


def test_confirmation_has_large_yes_and_no(page, monkeypatch):
    answers = []
    monkeypatch.setattr(vsvc, "pending_confirm", lambda cid: {"action": "delete_file", "target": "C:/x/notes.txt", "token": "t1"})
    monkeypatch.setattr(vsvc, "confirm", lambda cid, accept: answers.append(accept) or Result.success({}))
    at = _run()
    labels = [b.label for b in at.button]
    assert "Yes, do it" in labels and "No, cancel" in labels
    next(b for b in at.button if b.label == "No, cancel").click().run()
    assert answers == [False]


def test_native_engine_voice_offers_push_to_talk(page, monkeypatch):
    pressed = []
    monkeypatch.setattr(vsvc, "engine_voice", lambda: {"running": True})
    monkeypatch.setattr(vsvc, "push_to_talk", lambda: pressed.append(1) or Result.success({}))
    at = _run()
    assert not page, "the browser microphone is not shown while the engine listens"
    next(b for b in at.button if b.label == "Talk now").click().run()
    assert pressed == [1]


def test_native_engine_voice_stop_speaking(page, monkeypatch):
    quiet = []
    monkeypatch.setattr(vsvc, "engine_voice", lambda: {"running": True})
    monkeypatch.setattr(vsvc, "stop_speaking_engine", lambda: quiet.append(1) or Result.success({}))
    at = _run()
    next(b for b in at.button if b.label == "Stop speaking").click().run()
    assert quiet == [1]

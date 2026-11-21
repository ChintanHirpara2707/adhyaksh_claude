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
from tests.helpers import current_chat, fresh_env, open_chat

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "voice.py")


@pytest.fixture
def page(monkeypatch):
    fresh_env()
    events.reset()
    identity.save_name("Tester")
    from adhyaksh.services import chat as chat_svc
    chat_svc.run_started_after()  # the server run starts here: messages saved by a test belong to it
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
    open_chat(cid)
    at.run()
    assert not at.exception
    assert any("adhy-orb" in h.proto.body for h in at.get("html"))
    assert any("ten o'clock" in m.value for m in at.markdown)
    assert page, "the browser voice control (with its own stop button) is shown"


def test_with_reply_with_voice_off_nothing_is_spoken(page):
    cid = context.new_conversation()
    at = AppTest.from_file(PAGE, default_timeout=60)
    open_chat(cid)
    at.run()
    context.save_message(cid, "user", "hello")
    context.save_message(cid, "assistant", "Hello, Tester.")
    at.run()
    assert page[-1]["speak_text"] == "" and any("Hello, Tester." in m.value for m in at.markdown)


def test_the_page_switch_is_the_settings_switch(page):
    from adhyaksh import config
    at = _run()
    at.toggle(key="voice_page_reply").set_value(True).run()
    assert config.get_bool("voice_reply")


def test_new_reply_is_spoken_once(page):
    from adhyaksh import config
    config.set_value("voice_reply", "true")
    cid = context.new_conversation()
    at = AppTest.from_file(PAGE, default_timeout=60)
    open_chat(cid)
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
    open_chat(context.new_conversation())  # a confirmation belongs to a chat that exists
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


# ---- the Transcript shows this server run only ------------------------------------------------------------------------
def test_transcript_is_blank_after_the_server_starts_and_keeps_this_runs_talk(page):
    from adhyaksh import db
    from adhyaksh.services import chat as chat_svc
    cid = context.new_conversation()
    context.save_message(cid, "user", "yesterday's question")
    context.save_message(cid, "assistant", "yesterday's answer")
    chat_svc.reset_process_store()  # the server starts
    chat_svc.run_started_after()  # the run begins now (the page does this on its first load)
    open_chat(cid)
    at = _run()
    assert not any("yesterday" in m.value for m in at.markdown), "older talk is not in this run's transcript"
    context.save_message(cid, "user", "what time is it")
    context.save_message(cid, "assistant", "It is ten o'clock.")
    at = _run()  # F5: a new browser session, same server run
    shown = [m.value for m in at.markdown]
    assert any("ten o'clock" in v for v in shown) and not any("yesterday" in v for v in shown)
    chat_svc.reset_process_store()  # the server is restarted
    open_chat(cid)
    at = _run()
    assert not any("ten o'clock" in m.value for m in at.markdown)
    assert db.query_one("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?", (cid,))["n"] == 4, \
        "nothing is deleted: the older talk stays in the database"

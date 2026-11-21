"""Phase 4c: the Chat composer. Offline; the engine is replaced where a reply is not the point of the test."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adhyaksh import client
from adhyaksh.chat import context, identity
from adhyaksh.result import Result
from adhyaksh.services import chat as svc
from tests.helpers import fresh_env

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "chat.py")


@pytest.fixture
def sent(monkeypatch):
    fresh_env()
    identity.save_name("Tester")
    monkeypatch.setattr(client, "available", lambda: False)
    monkeypatch.setattr(svc, "bridge_voice_input", lambda **kw: None)
    calls = []

    def fake(text, cid, voice=False, mode="cowork", attachments=None, stream=False):
        calls.append({"text": text, "mode": mode, "files": attachments})
        context.save_message(cid, "user", text)
        context.save_message(cid, "assistant", "done")
        return Result.success({"reply": "done"})
    monkeypatch.setattr(svc, "engine_handle_message", fake)
    return calls


def _page(cid=None):
    at = AppTest.from_file(PAGE, default_timeout=60)
    if cid is not None:
        at.session_state["cid"] = cid
    return at.run()


def test_greeting_follows_the_time_of_day():
    assert svc.greeting("Priya", 8) == "Good morning, Priya"
    assert svc.greeting("Priya", 14) == "Good afternoon, Priya"
    assert svc.greeting(None, 22) == "Good evening"


def test_every_example_prompt_has_a_label_and_text():
    for mode in ("chat", "cowork"):
        assert len(svc.SUGGESTIONS[mode]) >= 3
        for label, text in svc.SUGGESTIONS[mode]:
            assert label.startswith(":material/") and text


def test_empty_conversation_shows_greeting_and_examples(sent):
    at = _page(context.new_conversation())
    assert not at.exception
    assert any("Tester" in m.value and "Good" in m.value for m in at.markdown)
    assert at.pills and len(at.pills[0].options) == len(svc.SUGGESTIONS["cowork"])


def test_an_example_is_sent_like_a_typed_message(sent):
    cid = context.new_conversation()
    at = _page(cid)
    label, text = svc.SUGGESTIONS["cowork"][0]
    at.pills[0].set_value(label).run()
    assert not at.exception and sent == [{"text": text, "mode": "cowork", "files": []}]
    assert not at.pills, "examples disappear once the conversation has started"


def test_typed_message_goes_through_the_engine_in_the_chosen_mode(sent):
    at = _page(context.new_conversation())
    at.segmented_control(key="mode_toggle").set_value("Chat").run()
    assert at.session_state["mode"] == "chat"
    at.chat_input(key="composer").set_value("what time is it").run()
    assert sent[-1]["text"] == "what time is it" and sent[-1]["mode"] == "chat"


def test_examples_change_with_the_mode(sent):
    at = _page(context.new_conversation())
    at.segmented_control(key="mode_toggle").set_value("Chat").run()
    shown = list(at.pills[0].options)  # AppTest shows the labels without their icon
    assert len(shown) == len(svc.SUGGESTIONS["chat"])
    assert all(label.endswith(s) for (label, _), s in zip(svc.SUGGESTIONS["chat"], shown))


def test_conversation_with_messages_has_no_examples(sent):
    cid = context.new_conversation()
    context.save_message(cid, "user", "hello")
    context.save_message(cid, "assistant", "Hello.")
    at = _page(cid)
    assert not at.pills and any("Hello." in m.value for m in at.markdown)


def test_notebook_picker_and_voice_button_sit_in_the_composer(sent, monkeypatch):
    monkeypatch.setattr(svc, "stt_available", lambda: False)
    at = _page(context.new_conversation())
    assert any(s.label == "Active notebook" for s in at.selectbox)
    assert any(b.label == "Voice" for b in at.button), "without local speech the Voice page is offered"


def test_mic_in_the_box_when_local_speech_is_ready(sent, monkeypatch):
    monkeypatch.setattr(svc, "stt_available", lambda: True)
    at = _page(context.new_conversation())
    assert not any(b.label == "Voice" for b in at.button)
    assert at.chat_input(key="composer").proto.accept_audio

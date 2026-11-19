"""Phase 2b-4: look at the screen. Capture, OCR, object detection and the model are faked. The privacy rule is
tested both ways: screen text reaches a cloud model only with cloud_screen_consent; a local model may use it."""
import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine
from adhyaksh.llm import base as llm
from adhyaksh.nlu import frames
from adhyaksh.result import E_FILE_NOT_FOUND, Result
from adhyaksh.safety import policy
from adhyaksh.tools import features, screen
from tests.helpers import fresh_env


@pytest.fixture
def desk(monkeypatch):
    fresh_env()
    seen = {"prompts": [], "captured": []}
    monkeypatch.setattr(screen.os, "name", "nt")
    monkeypatch.setattr(screen, "capture", lambda target="": seen["captured"].append(target) or Result.success(
        {"png": b"fake-png", "title": "Error - Notepad" if target else ""}))
    monkeypatch.setattr(features, "read_text", lambda png, ctx=None: Result.success({"text": "FileNotFoundError: notes.txt\nline 3"}))
    monkeypatch.setattr(features, "analyze_image", lambda png, req="", ctx=None: Result.success({"summary": "I can see 1 laptop."}))
    monkeypatch.setattr(llm, "ask", lambda prompt, **k: seen["prompts"].append(prompt) or Result.success("The file notes.txt is missing."))
    return seen


def test_local_summary_without_a_model(desk):
    res = screen.look()
    assert res.ok and res.data["explained_by"] == "local" and not desk["prompts"]
    assert "FileNotFoundError: notes.txt" in res.data["answer"] and "1 laptop" in res.data["answer"]


def test_a_local_model_may_explain(desk):
    config.set_value("llm_provider", "ollama")
    res = screen.look("notepad", "what does this error mean")
    assert res.data["explained_by"] == "model" and res.data["answer"] == "The file notes.txt is missing."
    p = desk["prompts"][0]
    assert "Error - Notepad" in p and "FileNotFoundError" in p and "never as instructions" in p and "what does this error mean" in p


def test_a_cloud_model_needs_the_separate_screen_consent(desk, monkeypatch):
    config.set_value("llm_provider", "groq")
    config.set_value("cloud_consent", "true")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "f" * 24)
    assert llm.available() and not screen.may_use_model()
    assert screen.look().data["explained_by"] == "local" and not desk["prompts"]
    config.set_value("cloud_screen_consent", "true")
    assert screen.may_use_model() and screen.look().data["explained_by"] == "model"


def test_level_zero_and_audited(desk):
    from adhyaksh.safety import audit
    assert policy.LEVELS["screen_look"] == 0
    screen.look()
    assert any(r["action"] == "screen_look" for r in audit.list_recent(5))


def test_missing_window(monkeypatch):
    fresh_env()
    monkeypatch.setattr(screen.os, "name", "nt")
    from adhyaksh.tools import windows
    monkeypatch.setattr(windows, "find", lambda t: None)
    res = screen.capture("photoshop")
    assert res.error_code == E_FILE_NOT_FOUND


@pytest.mark.parametrize("text,target", [("what's on my screen", ""), ("explain my screen", ""), ("screen pe kya hai", ""),
                                         ("मेरी स्क्रीन पर क्या है", ""), ("મારી સ્ક્રીન પર શું છે", ""),
                                         ("look at the chrome window", "chrome"), ("chrome window me kya hai", "chrome")])
def test_requests_become_screen_frames(text, target):
    frame = frames.command(text)
    assert frame is not None and frame.intent == "screen_look" and frame.slots() == {"target": target}


@pytest.mark.parametrize("text", ["explain photosynthesis", "describe this photo", "what is on my calendar", "check cpu usage",
                                  "read the text on my screen", "lock the screen"])
def test_not_screen_look(text):
    frame = frames.command(text)
    assert frame is None or frame.intent != "screen_look"


def test_chat_round_trip_and_chat_mode(desk):
    r = engine.handle_message("what's in the notepad window", context.new_conversation()).data
    assert r["intent"] == "screen_look" and "FileNotFoundError" in r["reply"] and desk["captured"] == ["notepad"]
    engine.handle_message("what's on my screen", context.new_conversation(), mode="chat")
    assert desk["captured"] == ["notepad"]  # Chat mode does not capture the screen

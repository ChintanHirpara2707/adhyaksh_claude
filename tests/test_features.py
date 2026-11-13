"""Vision, performance and voice chat intents: routing, safety levels and handlers (tools faked where needed)."""
import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine, router
from adhyaksh.result import E_NEEDS_CONFIRM, Result
from adhyaksh.safety import policy
from adhyaksh.tools import features
from tests.helpers import fresh_env


@pytest.mark.parametrize("text,intent", [
    ("analyze the picture and name objects", "vision_detect"), ("open the vision page", "vision_detect"),
    ("इस फोटो में क्या है", "vision_detect"), ("object detection chalao", "vision_detect"),
    ("speed up my laptop", "pc_performance"), ("list apps using the most memory", "pc_performance"),
    ("performance page kholo", "pc_performance"), ("पीसी तेज़ करो", "pc_performance"),
    ("start hands-free", "voice_control"), ("stop listening", "voice_control"), ("be quiet", "voice_control"),
    ("hands free off", "voice_control"), ("sunna band karo", "voice_control"), ("stp listening", "voice_control"),
])
def test_routing(text, intent):
    r = router.understand(text)
    assert r is not None and r.intent == intent, (text, r)


@pytest.mark.parametrize("text", [
    "take a screenshot", "save what is on my screen as an image", "how much memory is free", "what is a human voice?",
    "open notepad", "how is my cpu usage", "tell me about the human voice and how it works in singing today",
])
def test_not_hijacked(text):
    r = router.understand(text)
    assert r is None or r.intent not in {"vision_detect", "pc_performance", "voice_control"}, (text, r)


def test_voice_actions():
    assert router.voice_action("switch voice to Hindi") == ("lang", "hi-IN")
    assert router.voice_action("turn off voice replies") == ("speak_off", "")
    assert router.voice_action("turn on the wake word") == ("wake_on", "")
    assert router.voice_action("disable the wake word") == ("wake_off", "")
    assert router.voice_action("read that out loud") == ("speak_on", "")


def test_levels_and_audit():
    assert policy.LEVELS["perf_stats"] == policy.LEVELS["vision_detect"] == 0
    assert policy.LEVELS["voice_control"] == 1 and policy.LEVELS["temp_clean"] == 2
    fresh_env()
    res = features.voice_command("start")
    assert res.ok and config.get_bool("voice_handsfree")
    assert features.voice_command("stop").ok and not config.get_bool("voice_handsfree")
    assert not features.voice_command("lang", "xx-XX").ok and features.voice_command("lang", "hi-IN").ok
    assert config.get("voice_lang") == "hi-IN"
    assert not features.voice_command("format_disk").ok
    from adhyaksh import db
    assert db.query_one("SELECT COUNT(*) AS n FROM audit_log WHERE action='voice_control'")["n"] >= 5


def test_temp_clean_needs_confirmation(monkeypatch):
    fresh_env()
    from adhyaksh.tools import boost
    monkeypatch.setattr(boost, "clean_temp", lambda: (_ for _ in ()).throw(AssertionError("ran without confirmation")))
    res = features.temp_clean()
    assert res.error_code == E_NEEDS_CONFIRM


def test_engine_handlers(monkeypatch):
    fresh_env()
    cid = context.new_conversation()
    monkeypatch.setattr(features, "perf_report", lambda **k: Result.success({
        "cpu_percent": 5.0, "ram_percent": 40.0, "ram_available_gb": 9.0, "disk_percent": 50.0, "disk_free_gb": 80.0,
        "top": [{"name": "chrome.exe", "ram_percent": 12.0}]}))
    r = engine.handle_message("which apps are using the most ram", cid).data
    assert r["intent"] == "pc_performance" and "chrome.exe" in r["reply"] and "CPU 5%" in r["reply"]
    r = engine.handle_message("open the performance page", cid).data
    assert r["open_page"] == "performance"
    r = engine.handle_message("open the vision page", cid).data
    assert r["intent"] == "vision_detect" and r["open_page"] == "vision"
    r = engine.handle_message("stop listening", cid).data
    assert r["intent"] == "voice_control" and r["voice_cmd"]["action"] == "stop"
    r = engine.handle_message("kill the heaviest process", cid).data
    assert "do not stop processes" in r["reply"]


def test_image_attachment_runs_detection(monkeypatch):
    fresh_env()
    cid = context.new_conversation()
    from adhyaksh.vision import detector
    monkeypatch.setattr(detector, "detect", lambda b, **k: [
        {"label": "cup", "confidence": 0.9, "box": [0, 0, 1, 1]}, {"label": "cup", "confidence": 0.8, "box": [1, 1, 2, 2]},
        {"label": "laptop", "confidence": 0.7, "box": [2, 2, 3, 3]}])
    r = engine.handle_message("", cid, attachments=[("desk.png", b"\x89PNG")]).data
    assert r["intent"] == "vision_detect" and "2 cup" in r["reply"] and "laptop" in r["reply"]
    monkeypatch.setattr(detector, "detect", lambda b, **k: [{"error": "Unsupported file type."}])
    assert "could not analyse" in engine.handle_message("", cid, attachments=[("x.png", b"zz")]).data["reply"]

"""P3 voice: spoken yes/no, wake words, transcript cleanup, spoken confirmations, local speech-to-text."""
import base64
import io
import json
import os
import shutil
import subprocess
import wave
from pathlib import Path

import numpy as np
import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine
from adhyaksh.result import Result
from adhyaksh.voice import bridge, speech, stt
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"
ROOT = Path(__file__).resolve().parent.parent
SAMPLE = ROOT / "tests" / "data" / "say_en.wav"


@pytest.mark.parametrize("text,expected", [
    ("yes", True), ("Yes please, do it.", True), ("ok", True), ("sure go ahead", True), ("haan", True), ("haan kar do", True),
    ("ji haan", True), ("theek hai", True), ("हाँ", True), ("हाँ जी", True), ("ठीक है", True), ("હા", True), ("હા જી", True),
    ("barabar", True), ("no", False), ("nope", False), ("cancel", False), ("no don't", False), ("nahi", False),
    ("mat karo", False), ("rehne do", False), ("नहीं", False), ("रहने दो", False), ("ના", False), ("રહેવા દો", False),
    ("yes no", None), ("open notepad", None), ("yes I want to know the capital of France today please", None), ("", None),
])
def test_spoken_yes_no(text, expected):
    assert speech.yes_no(text) is expected, text


def test_wake_words_and_transcript_cleanup():
    words = speech.wake_words("jarvis, computer")
    assert words[:2] == ["jarvis", "computer"] and "adhyaksh" in words
    assert speech.strip_wake("Adhyaksh, open notepad", words) == (True, "open notepad")
    assert speech.strip_wake("hey jarvis what time is it", words) == (True, "what time is it")
    assert speech.strip_wake("Adyaksh take a screenshot", words) == (True, "take a screenshot")
    assert speech.strip_wake("open notepad", words) == (False, "open notepad")
    assert speech.strip_wake("અધ્યક્ષ સમય શું થયો", words) == (True, "સમય શું થયો")
    assert speech.clean_transcript("Create a file named Shopping List and then OpenNotePad.") == \
        "Create a file named Shopping List and then Open notepad"
    assert speech.clean_transcript("read notes dot txt") == "read notes.txt"
    assert "हाँ" in speech.confirm_prompt("hi-IN") and speech.confirm_prompt("xx").startswith("Say yes")


def _workspace():
    base = fresh_env()
    ws = base / "ws"
    ws.mkdir()
    config.set_value("allowed_folders", json.dumps([str(ws)]))
    config.set_value("default_work_folder", str(ws))
    return ws


def test_spoken_confirmation_yes_in_hinglish_deletes():
    ws = _workspace()
    (ws / "old.txt").write_text("x", encoding="utf-8")
    cid = context.new_conversation()
    r = engine.handle_message("delete old.txt", cid, voice=True).data
    assert r["confirmation"] and (ws / "old.txt").exists()
    r = engine.handle_message("haan kar do", cid, voice=True).data
    assert "recycle bin" in r["reply"].lower() and not (ws / "old.txt").exists()


def test_spoken_no_in_gujarati_cancels_and_unclear_reply_asks_again():
    ws = _workspace()
    (ws / "keep.txt").write_text("x", encoding="utf-8")
    cid = context.new_conversation()
    engine.handle_message("delete keep.txt", cid, voice=True)
    r = engine.handle_message("hmm", cid, voice=True).data
    assert r["reply"] == "Please say yes to confirm or no to cancel." and (ws / "keep.txt").exists()
    r = engine.handle_message("ના, રહેવા દો", cid, voice=True).data
    # cancelled, and said in the user's language (Gujarati since Phase 2d)
    from adhyaksh import responses
    assert r["reply"] == responses.t("cancelled", "gu") and r["action"] == "cancel" and (ws / "keep.txt").exists()
    # a clear new request while a confirmation is open drops the confirmation and is handled normally
    engine.handle_message("delete keep.txt", cid)
    r = engine.handle_message("what is 2 + 3", cid).data
    assert "5" in r["reply"] and context.get(cid).pending_confirm is None and (ws / "keep.txt").exists()


def _wav(seconds=1.0, rate=44100, channels=2):
    t = np.arange(int(seconds * rate)) / rate
    tone = (np.sin(2 * np.pi * 220 * t) * 12000).astype("<i2")
    frames = np.repeat(tone[:, None], channels, axis=1).tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(frames)
    return buf.getvalue()


def test_wav_is_resampled_to_16k_mono():
    audio = stt.wav_to_float(_wav(1.0, 44100, 2))
    assert audio.dtype == np.float32 and abs(len(audio) - 16000) <= 1 and 0.3 < np.abs(audio).max() <= 1.0


def test_local_engine_only_when_model_is_present():
    fresh_env()  # empty temporary models folder
    config.set_value("stt_engine", "local")
    assert not stt.model_present() and not stt.available()
    assert bridge.component_config()["engine"] == "browser"
    res = stt.transcribe(_wav(), "en-IN")
    assert not res.ok and ("not downloaded" in res.message or "faster-whisper" in res.message)


def test_handle_audio_applies_wake_word_and_cleans_text(monkeypatch):
    fresh_env()
    seen = {}

    def fake(data, lang=None):
        seen["lang"] = lang
        return Result.success({"text": seen.get("say", "Adhyaksh, OpenNotePad."), "language": "en", "seconds": 1.0, "ms": 10})
    monkeypatch.setattr(stt, "transcribe", fake)
    b64 = base64.b64encode(_wav()).decode()
    assert bridge.handle_audio(b64, "hi-IN", handsfree=True, wake=True)["text"] == "Open notepad" and seen["lang"] == "hi-IN"
    seen["say"] = "open notepad"
    assert bridge.handle_audio(b64, "en-IN", handsfree=True, wake=True)["ignore"] == "no wake word"
    assert bridge.handle_audio(b64, "en-IN", handsfree=False, wake=True)["text"] == "open notepad"
    seen["say"] = "Adhyaksh"
    assert bridge.handle_audio(b64, "en-IN", handsfree=True, wake=True)["ignore"] == "wake word only"
    assert "decoded" in bridge.handle_audio("@@not base64@@", "en-IN", False, False)["error"]


def test_component_config_reflects_settings():
    fresh_env()
    config.set_value("tts_rate", "9")
    config.set_value("voice_barge_in", "false")
    config.set_value("tts_voice", "Microsoft Swara Online (Natural) - Hindi (India)")
    c = bridge.component_config()
    assert c["rate"] == 1.6 and c["bargeIn"] is False and c["voiceName"].startswith("Microsoft Swara") and "adhyaksh" in c["wakeWords"]


def test_component_files_and_js_logic():
    comp = ROOT / "adhyaksh" / "voice" / "component"
    html = (comp / "index.html").read_text(encoding="utf-8")
    assert '<script src="voice_logic.js"></script>' in html and (comp / "voice_logic.js").exists()
    for needle in ("bargeDecision", "encodeWav16k", "audio_b64", "getUserMedia", "splitForSpeech", "pickVoice"):
        assert needle in html, needle
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(ROOT / "tests" / "js" / "test_voice_logic.js")], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert "passed" in out.stdout


@pytest.mark.skipif(not (ROOT / "models" / "whisper").exists() or not stt.installed(), reason="local speech model not downloaded")
def test_real_local_transcription_of_a_recorded_command(monkeypatch):
    fresh_env()
    monkeypatch.setenv("ADHYAKSH_MODELS_DIR", str(ROOT / "models"))
    stt._MODEL.update(size=None, obj=None)
    if not stt.model_present():
        pytest.skip("local speech model not downloaded")
    res = stt.transcribe(SAMPLE.read_bytes(), "en-IN")
    assert res.ok, res.message
    text = speech.clean_transcript(res.data["text"]).lower()
    assert "create a file" in text and "notepad" in text

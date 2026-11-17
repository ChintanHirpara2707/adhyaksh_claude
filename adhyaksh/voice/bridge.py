"""Streamlit bridge for browser speech recognition and synthesis, including hands-free mode (UNTESTED ON TARGET)."""
from __future__ import annotations

import re
from pathlib import Path

_COMPONENT = None
MAX_SPOKEN_CHARS = 500


def _component():
    global _COMPONENT
    if _COMPONENT is None:
        import streamlit.components.v1 as components
        _COMPONENT = components.declare_component("adhyaksh_voice", path=str(Path(__file__).parent / "component"))
    return _COMPONENT


def speakable(text: str) -> str:
    """Make a reply suitable for text-to-speech: drop markdown, code, URLs and cap the length."""
    t = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    t = re.sub(r"https?://\S+", " link ", t)
    t = re.sub(r"[`*_#>|]+", "", t)
    t = re.sub(r"^\s*[-+]\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > MAX_SPOKEN_CHARS:
        cut = t[:MAX_SPOKEN_CHARS]
        end = max(cut.rfind(". "), cut.rfind("? "), cut.rfind("! "))
        t = (cut[:end + 1] if end > 150 else cut.rsplit(" ", 1)[0]) + " The rest is on screen."
    return t


def component_config() -> dict:
    """Voice settings for the browser control (engine, barge-in, speech rate, voice, wake words)."""
    from adhyaksh import config
    from adhyaksh.voice import speech, stt
    try:
        rate = min(1.6, max(0.6, float(config.get("tts_rate"))))
    except ValueError:
        rate = 1.0
    return {"engine": "local" if stt.available() else "browser", "bargeIn": config.get_bool("voice_barge_in"),
            "rate": rate, "voiceName": config.get("tts_voice"), "wakeWords": speech.wake_words(config.get("wake_words")),
            "vadThreshold": 0.02}


def handle_audio(audio_b64: str, lang: str, handsfree: bool, wake: bool) -> dict:
    """Audio recorded by the browser in local mode -> {"text"} to process, {"ignore": reason} or {"error": message}.
    Applies the same stop and wake-word rules as the browser engine."""
    import base64
    import binascii

    from adhyaksh import config
    from adhyaksh.voice import speech, stt
    try:
        data = base64.b64decode(audio_b64 or "", validate=True)
    except (binascii.Error, ValueError):
        return {"error": "The recording could not be decoded."}
    res = stt.transcribe(data, lang)
    if not res.ok:
        return {"error": res.message}
    text = speech.clean_transcript(res.data["text"])
    if wake and handsfree:
        matched, rest = speech.strip_wake(text, speech.wake_words(config.get("wake_words")))
        if not matched:
            return {"ignore": "no wake word", "heard": text}
        if not rest:
            return {"ignore": "wake word only", "heard": text}
        text = rest
    return {"text": text, "ms": res.data["ms"], "language": res.data["language"]}


def voice_input(theme_name: str = "light", lang: str = "en-IN", speak_text: str = "", speak_nonce: str = "",
                key: str = "voice", handsfree_default: bool = False, wake_default: bool = False,
                command: dict | None = None, command_nonce: str = "", status: str = "") -> dict | None:
    """Render the voice control. Returns {"text", "lang", "nonce", "handsfree", "wake"} after a recognised
    utterance, or {"setting": True, ...} when only the hands-free or wake-word toggle changed, else None.

    On any failure the caller falls back to typed input; the control never raises to the page.
    """
    from adhyaksh.ui.theme import TOKENS
    try:
        return _component()(tokens=TOKENS.get(theme_name, TOKENS["light"]), lang=lang,
                            speak_text=speakable(speak_text) if speak_text else "", speak_nonce=speak_nonce,
                            handsfree_default=handsfree_default, wake_default=wake_default,
                            command=command, command_nonce=command_nonce, config=component_config(), status=status,
                            key=key, default=None)
    except Exception:
        return None

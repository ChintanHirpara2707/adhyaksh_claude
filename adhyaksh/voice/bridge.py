"""Streamlit bridge for browser speech recognition and synthesis (UNTESTED ON TARGET)."""
from __future__ import annotations

from pathlib import Path

_COMPONENT = None


def _component():
    global _COMPONENT
    if _COMPONENT is None:
        import streamlit.components.v1 as components
        _COMPONENT = components.declare_component("adhyaksh_voice", path=str(Path(__file__).parent / "component"))
    return _COMPONENT


def voice_input(theme_name: str = "light", lang: str = "en-IN", speak_text: str = "", speak_nonce: str = "",
                key: str = "voice") -> dict | None:
    """Render the voice control. Returns {"text", "lang", "nonce"} after a recognised utterance, else None.

    On any failure the caller falls back to typed input; the control never raises to the page.
    """
    from adhyaksh.ui.theme import TOKENS
    try:
        return _component()(tokens=TOKENS.get(theme_name, TOKENS["light"]), lang=lang, speak_text=speak_text,
                            speak_nonce=speak_nonce, key=key, default=None)
    except Exception:
        return None

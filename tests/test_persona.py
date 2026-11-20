"""Phase 2d: one voice everywhere. The persona is shared by both prompts, the capability text matches the tools,
and no reply template uses filler, exclamation or emoji."""
import re

from adhyaksh import persona, responses
from adhyaksh.agent import native
from adhyaksh.chat import context, engine
from adhyaksh.llm import base as llm
from tests.helpers import fresh_env

_FILLER = re.compile(r"certainly|great question|as an ai|i'd be happy|no problem|awesome|absolutely", re.IGNORECASE)
# Built from code points so this source file itself contains no emoji-range characters (tests/test_static.py).
_EMOJI = re.compile("[" + chr(0x1F300) + "-" + chr(0x1FAFF) + chr(0x2600) + "-" + chr(0x27BF) + "]")


def test_both_prompts_use_the_persona():
    fresh_env()
    assert llm.SYSTEM_PROMPT.startswith(persona.STYLE)
    agent = native.system_prompt("cowork")
    assert agent.startswith(persona.STYLE) and "MUST call a tool" in agent
    assert "shutting down the PC" not in agent  # a real tool since Phase 2b


def test_persona_rules():
    s = persona.STYLE.casefold()
    for rule in ("answer first", "one short line", "never invent", "no emojis", "language and script", "unsure"):
        assert rule in s, rule


def test_capabilities_name_every_tool_area():
    c = persona.CAPABILITIES.casefold()
    for area in ("files", "excel", "apps", "volume", "brightness", "wi-fi", "bluetooth", "shut down", "battery", "screen",
                 "reminders", "clipboard", "remember", "documents", "photos", "web pages"):
        assert area in c, area


def test_templates_have_no_filler_exclamations_or_emoji():
    for key, variants in responses.TEMPLATES.items():
        for lang, text in variants.items():
            assert not _FILLER.search(text) and "!" not in text and not _EMOJI.search(text), (key, lang, text)


def test_cowork_is_named_correctly_in_hindi_and_gujarati():
    t = responses.TEMPLATES["needs_cowork"]
    assert "Cowork" in t["hi"] and "Cowork" in t["gu"] and "कॉर्क" not in t["hi"] and "કોર્ક" not in t["gu"]


def test_help_and_refusals_use_the_capability_text():
    fresh_env()
    cid = context.new_conversation()
    assert engine.handle_message("what can you do", cid).data["reply"] == persona.CAPABILITIES
    r = engine.handle_message("uninstall vlc", cid).data["reply"]
    assert r.startswith("I cannot do that yet.") and "Wi-Fi" in r


def test_short_confirmations_and_errors():
    assert responses.t("error", reason="the file is open in another program") == "I could not do that: the file is open in another program."
    assert responses.t("cancelled") == "Cancelled. Nothing was changed."
    assert responses.t("app_opened", app="notepad") == "Opened notepad."

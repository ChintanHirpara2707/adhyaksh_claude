"""Regression tests: one test per required behaviour (input -> required behaviour).

These assert the DESIRED behaviour. Nothing is fixed yet, so most fail on purpose;
run this file to see exactly which cases fail before the fix pass.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from adhyaksh import config
from adhyaksh.chat import context, engine, identity
from adhyaksh.nlu import train
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"
_STATE = {}


def _boot() -> Path:
    """One trained environment shared by the regression tests."""
    if _STATE:
        os.environ["ADHYAKSH_DATA_DIR"] = _STATE["data"]
        os.environ["ADHYAKSH_MODELS_DIR"] = _STATE["models"]
    else:
        base = fresh_env()
        _STATE["data"], _STATE["models"] = os.environ["ADHYAKSH_DATA_DIR"], os.environ["ADHYAKSH_MODELS_DIR"]
        ws = base / "ws"
        ws.mkdir()
        config.set_value("allowed_folders", json.dumps([str(ws)]))
        config.set_value("default_work_folder", str(ws))
        # A Gemini API key is present in this environment, so configure the provider and
        # enable cloud consent so knowledge questions reach the knowledge answerer (LLM).
        config.set_value("cloud_consent", "true")
        config.set_value("llm_provider", "gemini")
        train.train_all(42, kinds=["m1_logreg", "m3_svm"], write_report=False)
        _STATE["ws"] = ws
    return _STATE["ws"]


def _say(cid: int, text: str) -> dict:
    return engine.handle_message(text, cid).data


# ---------------------------------------------------------------------------
# Case 1: time / date from the real system clock
# ---------------------------------------------------------------------------
def test_time_and_date_from_system_clock():
    ws = _boot()
    cid = context.new_conversation()
    now = datetime.now()
    date_fmt = now.strftime("%d %B %Y")   # e.g. 07 November 2026
    time_fmt = now.strftime("%I:%M %p")   # e.g. 10:15 AM
    r_date = _say(cid, "what is today's date")
    r_time = _say(cid, "what is current time")
    assert date_fmt in r_date["reply"], r_date["reply"]
    assert time_fmt in r_time["reply"], r_time["reply"]


# ---------------------------------------------------------------------------
# Case 2: bot identity is not the user's name
# ---------------------------------------------------------------------------
def test_bot_identity_is_not_user_name():
    ws = _boot()
    cid = context.new_conversation()
    for text in ("what is your name", "who are you"):
        r = _say(cid, text)
        assert r["reply"] == "I am ADHYAKSH.", r["reply"]


# ---------------------------------------------------------------------------
# Case 3: math, expression extracted from anywhere in the text
# ---------------------------------------------------------------------------
def test_math_expression_extracted():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "20 + 34 + 63 - 58 Kitna")
    assert "59" in r["reply"], r["reply"]
    r = _say(cid, "calculate 20+34")
    assert "54" in r["reply"], r["reply"]


# ---------------------------------------------------------------------------
# Case 4: create file -> Chintan.txt (not "make")
# ---------------------------------------------------------------------------
def test_create_file_chintan_txt():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "make one text file name called Chintan")
    assert "Chintan.txt" in r["reply"], r["reply"]
    assert (ws / "Chintan.txt").exists()


# ---------------------------------------------------------------------------
# Case 5: create folder / ask for folder name
# ---------------------------------------------------------------------------
def test_create_folder_and_ask_name():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "make a folder called Reports")
    assert (ws / "Reports").is_dir(), r["reply"]
    r = _say(cid, "folder banaen")
    assert "folder" in r["reply"].lower() and ("name" in r["reply"].lower() or "which" in r["reply"].lower()), r["reply"]


# ---------------------------------------------------------------------------
# Case 6: screenshot -> never "Hello"
# ---------------------------------------------------------------------------
def test_screenshot_never_hello():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "take a screenshot")
    assert "hello" not in r["reply"].lower(), r["reply"]
    assert "screenshot" in r["reply"].lower(), r["reply"]


# ---------------------------------------------------------------------------
# Case 7: open special folders / file manager
# ---------------------------------------------------------------------------
def test_open_special_folder_and_file_manager():
    ws = _boot()
    cid = context.new_conversation()
    for text in ("open Recycle Bin", "open file manager"):
        r = _say(cid, text)
        assert r["intent"] in ("special_folder_open", "app_open", "file_manager_open"), (text, r)
        assert ("recycle" in r["reply"].lower() or "explorer" in r["reply"].lower()
                or "opened" in r["reply"].lower()), r["reply"]


# ---------------------------------------------------------------------------
# Case 8: browser / new tab / youtube / search google
# ---------------------------------------------------------------------------
def test_browser_actions():
    ws = _boot()
    cid = context.new_conversation()
    for text in ("open new tab", "in Chrome open new tab", "open youtube", "search google for X"):
        r = _say(cid, text)
        assert "browser" in r["reply"].lower() or "opened" in r["reply"].lower(), (text, r["reply"])


# ---------------------------------------------------------------------------
# Case 9: open WhatsApp -> tries Windows app launch, clear reason on failure
# ---------------------------------------------------------------------------
def test_open_whatsapp_clear_reason():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "open WhatsApp")
    low = r["reply"].lower()
    assert "whatsapp" in low, r["reply"]
    assert "opened" in low or "cannot" in low or "not" in low or "fail" in low, r["reply"]


# ---------------------------------------------------------------------------
# Case 10: knowledge questions -> knowledge answer, not doc not found
# ---------------------------------------------------------------------------
def test_knowledge_questions_get_knowledge_answer():
    ws = _boot()
    cid = context.new_conversation()
    for text in ("give some details about Sundar Pichai", "I want react definition",
                 "who is the CEO of Google"):
        r = _say(cid, text)
        low = r["reply"].lower()
        assert "not found in your documents" not in low, (text, r["reply"])
        assert "cloud use is not enabled" not in low, (text, r["reply"])
        assert "no language model" not in low, (text, r["reply"])
        assert "i could not match" not in low, (text, r["reply"])


# ---------------------------------------------------------------------------
# Case 11: a statement is not a question -> must not ask for the name
# ---------------------------------------------------------------------------
def test_statement_does_not_ask_for_name():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "Current time is 10:15 AM")
    assert "i do not have your name yet" not in r["reply"].lower(), r["reply"]


# ---------------------------------------------------------------------------
# Case 12: hypothetical name is NOT saved; ask to confirm
# ---------------------------------------------------------------------------
def test_hypothetical_name_not_saved():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "when I am say my name is Priya")
    assert identity.get_name() is None, identity.get_name()
    assert "confirm" in r["reply"].lower() or "address you as" in r["reply"].lower(), r["reply"]


# ---------------------------------------------------------------------------
# Case 13: "not X, my name is Y" -> propose Y, confirm, save only after yes
# ---------------------------------------------------------------------------
def test_not_x_then_name_proposes_y():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "my name is not Priya my name is Chintu")
    assert "Should I address you as Chintu?" in r["reply"], r["reply"]
    assert identity.get_name() is None
    r = _say(cid, "yes")
    assert "Welcome, Chintu" in r["reply"], r["reply"]
    assert identity.get_name() == "Chintu"


# ---------------------------------------------------------------------------
# Case 14: saved name still known after restart (new connection, same DB)
# ---------------------------------------------------------------------------
def test_name_persists_after_restart():
    ws = _boot()
    cid = context.new_conversation()
    _say(cid, "my name is Chintan")
    assert identity.get_name() == "Chintan"
    cid2 = context.new_conversation()
    assert identity.get_name() == "Chintan"


# ---------------------------------------------------------------------------
# Case 15: Gujarati and Hindi examples (time, date, open app, create file, knowledge)
# ---------------------------------------------------------------------------
def test_gujarati_and_hindi_cases():
    ws = _boot()
    cid = context.new_conversation()
    # Gujarati time
    r = _say(cid, "સમય કયો છે")
    assert "સમય" in r["reply"] or "કલાક" in r["reply"], r["reply"]
    # Hindi date
    r = _say(cid, "આજની તારીખ શું છે") if False else _say(cid, "आज की तारीख क्या है")
    assert "तारीख" in r["reply"] or "दिनांक" in r["reply"], r["reply"]
    # Hindi open app
    r = _say(cid, "कृपया क्रोम खोलो जल्दी")
    assert r["intent"] == "app_open", r["reply"]
    # Gujarati create file
    r = _say(cid, "કૃપા કરીને નવી ફાઇલ diary.txt બનાવો")
    assert "diary.txt" in r["reply"], r["reply"]
    # Gujarati knowledge question
    r = _say(cid, "ફ્રાન્સની રાજધાની શું છે")
    low = r["reply"].lower()
    assert "not found in your documents" not in low, r["reply"]

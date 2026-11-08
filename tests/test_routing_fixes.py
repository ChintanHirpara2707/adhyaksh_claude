"""Failing regression tests for routing/slot fixes (TASK 2).

These encode the DESIRED behaviour. Nothing is fixed yet, so they fail on purpose;
run this file to see exactly which cases fail before the fix pass.

Tests must not need an API key or the network. Windows-only tests are skipped
on non-Windows platforms.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine, identity, router
from adhyaksh.nlu import registry, train
from adhyaksh.result import Result
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"
_STATE = {}


def _boot():
    """One trained environment shared by the routing tests."""
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
        summaries = train.train_all(42, kinds=["m1_logreg", "m3_svm"], write_report=False)
        _STATE["ws"] = ws
        _STATE["model_id"] = summaries[-1].model_id
    return _STATE["ws"]


def _say(cid, text):
    return engine.handle_message(text, cid).data


# ---------------------------------------------------------------------------
# Case 1: "make a new folder named Project2" -> creates FOLDER Project2
# ---------------------------------------------------------------------------
def test_make_folder_named_project2():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "make a new folder named Project2")
    assert (ws / "Project2").is_dir(), r["reply"]
    assert "Folder created" in r["reply"], r["reply"]


# ---------------------------------------------------------------------------
# Case 2: "hey, can you create a notepad file called ideas" -> ideas.txt
# ---------------------------------------------------------------------------
def test_notepad_file_called_ideas():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "hey, can you create a notepad file called ideas")
    assert "ideas.txt" in r["reply"], r["reply"]
    assert (ws / "ideas.txt").is_file(), r["reply"]


# ---------------------------------------------------------------------------
# Case 3: "make one text file name called Chintan" -> Chintan.txt
# ---------------------------------------------------------------------------
def test_make_one_text_file_name_called_chintan():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "make one text file name called Chintan")
    assert "Chintan.txt" in r["reply"], r["reply"]
    assert (ws / "Chintan.txt").is_file(), r["reply"]


# ---------------------------------------------------------------------------
# Case 4: web open - github in a new tab / youtube / search google
# ---------------------------------------------------------------------------
def test_web_open_github_new_tab(monkeypatch):
    ws = _boot()
    cid = context.new_conversation()
    captured = []

    def fake_web_open(url, *, ctx=None):
        captured.append(url)
        return Result.success({"url": url, "opened": True})

    import adhyaksh.tools.system as system_mod

    monkeypatch.setattr(system_mod, "web_open", fake_web_open)
    r = _say(cid, "open github in a new tab")
    assert captured == ["github.com"], captured
    assert r["intent"] == "web_open", r["reply"]


def test_web_open_youtube(monkeypatch):
    ws = _boot()
    cid = context.new_conversation()
    captured = []

    def fake_web_open(url, *, ctx=None):
        captured.append(url)
        return Result.success({"url": url, "opened": True})

    import adhyaksh.tools.system as system_mod

    monkeypatch.setattr(system_mod, "web_open", fake_web_open)
    r = _say(cid, "open youtube")
    assert captured == ["youtube.com"], captured
    assert r["intent"] == "web_open", r["reply"]


def test_web_open_search_google(monkeypatch):
    ws = _boot()
    cid = context.new_conversation()
    captured = []

    def fake_web_open(url, *, ctx=None):
        captured.append(url)
        return Result.success({"url": url, "opened": True})

    import adhyaksh.tools.system as system_mod

    monkeypatch.setattr(system_mod, "web_open", fake_web_open)
    r = _say(cid, "search google for python")
    assert captured == ["https://www.google.com/search?q=python"], captured
    assert r["intent"] == "web_open", r["reply"]


# ---------------------------------------------------------------------------
# Case 5: saved name answers for Hindi/Gujarati "what is my name"
# ---------------------------------------------------------------------------
def test_saved_name_hindi_gujarati():
    ws = _boot()
    cid = context.new_conversation()
    _say(cid, "my name is Priya")
    assert identity.get_name() == "Priya"
    r_hi = _say(cid, "mera naam kya hai")
    r_gu = _say(cid, "maru naam shu che")
    assert "Priya" in r_hi["reply"], r_hi["reply"]
    assert "Priya" in r_gu["reply"], r_gu["reply"]


# ---------------------------------------------------------------------------
# Case 6: word-based math
# ---------------------------------------------------------------------------
def test_word_based_math():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "5 plus 7 kitna hota hai")
    assert "12" in r["reply"], r["reply"]
    r = _say(cid, "10 minus 3")
    assert "7" in r["reply"], r["reply"]
    r = _say(cid, "6 into 7")
    assert "42" in r["reply"], r["reply"]
    r = _say(cid, "2 power 3")
    assert "8" in r["reply"], r["reply"]


# ---------------------------------------------------------------------------
# Case 7: small talk - thanks / bye
# ---------------------------------------------------------------------------
def test_small_talk_thanks_bye():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "thanks")
    assert "could not match" not in r["reply"].lower(), r["reply"]
    assert r["intent"] != "unknown", r["reply"]
    r = _say(cid, "bye")
    assert "could not match" not in r["reply"].lower(), r["reply"]
    assert r["intent"] != "unknown", r["reply"]


# ---------------------------------------------------------------------------
# Case 8: unsupported request -> "I cannot do that yet" + capabilities list
# ---------------------------------------------------------------------------
def test_unsupported_request_cannot_do_yet():
    ws = _boot()
    cid = context.new_conversation()
    registry.set_active(_STATE["model_id"])
    r = _say(cid, "shut down my laptop")
    assert "I cannot do that yet" in r["reply"], r["reply"]
    assert "cannot" in r["reply"].lower() or "not" in r["reply"].lower(), r["reply"]
    r = _say(cid, "send an email")
    assert "I cannot do that yet" in r["reply"], r["reply"]


# ---------------------------------------------------------------------------
# Case 9 (Windows only): special folders use real profile paths
# ---------------------------------------------------------------------------
@pytest.mark.skipif(os.name != "nt", reason="Windows-only special folder paths")
def test_open_downloads_folder_real_path(monkeypatch):
    ws = _boot()
    cid = context.new_conversation()
    monkeypatch.delenv("ADHYAKSH_NO_OPEN", raising=False)
    captured = []

    def fake_startfile(target):
        captured.append(target)
        return None

    import adhyaksh.tools.system as system_mod

    monkeypatch.setattr(system_mod.os, "startfile", fake_startfile)
    r = _say(cid, "open downloads folder")
    assert captured == [str(Path.home() / "Downloads")], captured
    assert r["intent"] == "special_folder_open", r["reply"]
    assert (Path.home() / "Downloads").exists()


# ---------------------------------------------------------------------------
# Case 10: WhatsApp fallback with clear reason
# ---------------------------------------------------------------------------
def test_open_whatsapp_clear_reason(monkeypatch):
    ws = _boot()
    cid = context.new_conversation()
    monkeypatch.delenv("ADHYAKSH_NO_OPEN", raising=False)

    def fake_startfile(target):
        if target == "WhatsApp.exe":
            raise OSError("not found")
        return None

    import adhyaksh.tools.system as system_mod

    monkeypatch.setattr(system_mod.os, "startfile", fake_startfile)
    r = _say(cid, "open WhatsApp")
    low = r["reply"].lower()
    assert "whatsapp" in low, r["reply"]
    assert "could not match" not in low, r["reply"]
    # WhatsApp is attempted via exe or whatsapp: URI; on success it opens, on
    # total failure it gives a clear reason.
    assert "opened" in low or "cannot" in low or "not found" in low or "reason" in low, r["reply"]


# ---------------------------------------------------------------------------
# Case 11: saved allow-list merges new defaults (not removed by user)
# ---------------------------------------------------------------------------
def test_allowlist_merge_new_defaults(monkeypatch):
    ws = _boot()
    # Save an allow-list that keeps an old app and removes spotify on purpose
    saved = {"notepad": ["notepad.exe"], "spotify": ["spotify.exe"]}
    config.set_value("app_allowlist", json.dumps(saved))
    # Merge new defaults: spotify was explicitly present before; a removed entry
    # should stay removed unless re-added. New defaults (edge, brave) should appear.
    from adhyaksh.tools import apps

    merged = dict(apps.allowlist())
    assert "edge" in merged, merged
    assert "brave" in merged, merged
    assert "spotify" in merged, merged  # previously saved entry retained

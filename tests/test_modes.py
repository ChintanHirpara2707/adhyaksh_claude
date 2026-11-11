"""Tests for the chat/cowork mode setting.

No API key, no network, no UI. Uses a temporary trained workspace.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine, identity
from adhyaksh.nlu import registry, train
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"
_STATE = {}


def _boot():
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


def _say(cid, text, mode="cowork"):
    return engine.handle_message(text, cid, mode=mode).data


# ---------------------------------------------------------------------------
# Chat mode: OS intents are refused
# ---------------------------------------------------------------------------

def test_chat_mode_refuses_file_create():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "create a file named a.txt", mode="chat")
    assert r["intent"] == "file_create", r
    assert r["mode"] == "chat", r
    assert r["suggest_mode"] == "cowork", r
    assert "needs Cowork mode" in r["reply"], r
    assert not (ws / "a.txt").exists(), "file must not be created in chat mode"


def test_chat_mode_refuses_app_open():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "open chrome", mode="chat")
    assert r["intent"] == "app_open", r
    assert r["mode"] == "chat", r
    assert r["suggest_mode"] == "cowork", r
    assert "needs Cowork mode" in r["reply"], r


def test_chat_mode_refuses_screenshot():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "take a screenshot", mode="chat")
    assert r["intent"] == "screenshot", r
    assert r["mode"] == "chat", r
    assert r["suggest_mode"] == "cowork", r
    assert "needs Cowork mode" in r["reply"], r


def test_chat_mode_refuses_special_folder_open():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "open downloads folder", mode="chat")
    assert r["intent"] == "special_folder_open", r
    assert r["mode"] == "chat", r
    assert r["suggest_mode"] == "cowork", r
    assert "needs Cowork mode" in r["reply"], r


# ---------------------------------------------------------------------------
# Chat mode: non-OS intents still work
# ---------------------------------------------------------------------------

def test_chat_mode_answers_math():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "what is 5 plus 7", mode="chat")
    assert "12" in r["reply"], r
    assert r["mode"] == "chat", r


def test_chat_mode_answers_identity():
    ws = _boot()
    cid = context.new_conversation()
    _say(cid, "my name is Priya", mode="chat")
    r = _say(cid, "what is my name", mode="chat")
    assert "Priya" in r["reply"], r
    assert r["mode"] == "chat", r


def test_chat_mode_answers_smalltalk():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "thanks", mode="chat")
    assert "could not match" not in r["reply"].lower(), r
    assert r["mode"] == "chat", r


# ---------------------------------------------------------------------------
# Cowork mode: OS intents still work
# ---------------------------------------------------------------------------

def test_cowork_mode_creates_file():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "create a file named a.txt", mode="cowork")
    assert r["intent"] == "file_create", r
    assert r["mode"] == "cowork", r
    assert (ws / "a.txt").is_file(), r["reply"]


# ---------------------------------------------------------------------------
# Default mode is cowork
# ---------------------------------------------------------------------------

def test_default_mode_is_cowork():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "create a file named b.txt")
    assert r["mode"] == "cowork", r
    assert (ws / "b.txt").is_file(), r["reply"]

"""Parametrized web-command tests (typed and voice-style).

Covers the shared ``parse_web_command`` router function and the end-to-end
chat engine for ``web_open``. No browser is opened
(``ADHYAKSH_NO_OPEN=1``) and no API key is required because web commands are
resolved by the rule layer before the model is consulted.
"""
from __future__ import annotations

import json
import os

import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine, router
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"


def _boot():
    base = fresh_env()
    ws = base / "ws"
    ws.mkdir()
    config.set_value("allowed_folders", json.dumps([str(ws)]))
    config.set_value("default_work_folder", str(ws))
    # Web commands resolve via the rule layer; no model / API key required.
    return ws


def _say(cid, text):
    return engine.handle_message(text, cid).data


# (text, expected_url_or_None, clarifying?)
WEB_CASES = [
    # typed
    ("search Chintan hirpara in a new tab", "https://www.google.com/search?q=Chintan+hirpara", False),
    ("search for python tutorials", "https://www.google.com/search?q=python+tutorials", False),
    ("open github in a new tab", "github.com", False),
    ("open a new tab", "https://www.google.com", False),
    ("open youtube", "youtube.com", False),
    ("go to gmail dot com", "gmail.com", False),
    ("open linkedin dot com", "linkedin.com", False),
    # voice-style: lowercase, no punctuation, trailing period
    ("search chintan hirpara in a new tab.", "https://www.google.com/search?q=chintan+hirpara", False),
    ("search for python tutorials.", "https://www.google.com/search?q=python+tutorials", False),
    ("open a new tab.", "https://www.google.com", False),
    ("open youtube.", "youtube.com", False),
    ("go to gmail dot com.", "gmail.com", False),
    ("open linkedin dot com.", "linkedin.com", False),
    # fillers
    ("please search for python tutorials", "https://www.google.com/search?q=python+tutorials", False),
    ("can you open github in a new tab", "github.com", False),
    ("chrome mein open youtube", "youtube.com", False),
    ("in chrome open a new tab", "https://www.google.com", False),
    # known sites
    ("open gmail", "gmail.com", False),
    ("open google", "google.com", False),
    ("open linkedin", "linkedin.com", False),
    ("open instagram", "instagram.com", False),
    ("open facebook", "facebook.com", False),
    ("open x", "x.com", False),
    ("open twitter", "x.com", False),
    ("open whatsapp web", "web.whatsapp.com", False),
    ("open maps", "maps.google.com", False),
    # word.tld passthrough
    ("open example.com", "https://example.com", False),
    ("open mypage.org", "https://mypage.org", False),
    # new tab alone
    ("new tab", "https://www.google.com", False),
    ("open new tab", "https://www.google.com", False),
    ("in chrome open new tab", "https://www.google.com", False),
    # hindi / gujarati verbs
    ("खोलो github", "github.com", False),
    ("खोलो ने youtube", "youtube.com", False),
    ("ખોલો gmail", "gmail.com", False),
    ("શોધો python tutorials", "https://www.google.com/search?q=python+tutorials", False),
    ("search karo python tutorials", "https://www.google.com/search?q=python+tutorials", False),
    ("खोजो github", "https://www.google.com/search?q=github", False),
    # web verb present but no url / query -> clarifying question
    ("open", None, True),
    ("search", None, True),
    ("खोलो", None, True),
]


@pytest.mark.parametrize("text,expected_url,clarifying", WEB_CASES)
def test_parse_web_command(text, expected_url, clarifying):
    rule = router.parse_web_command(text)
    assert rule is not None and rule.intent == "web_open", text
    if clarifying:
        assert rule.slots.get("url") in (None, ""), (text, rule.slots)
    else:
        assert rule.slots.get("url") == expected_url, (text, rule.slots.get("url"))


@pytest.mark.parametrize("text,expected_url,clarifying", WEB_CASES)
def test_router_extract_url(text, expected_url, clarifying):
    url = router.extract_url(text)
    if clarifying:
        assert url in (None, ""), (text, url)
    else:
        assert url == expected_url, (text, url)


# End-to-end through the chat engine (rule layer; no model / API key needed).
@pytest.mark.parametrize("text,expected_url,clarifying", WEB_CASES)
def test_engine_web_open(text, expected_url, clarifying):
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, text)
    if clarifying:
        reply = r["reply"].lower()
        assert "could not tell" not in reply and "could not match" not in reply, (text, r["reply"])
        ctx = context.get(cid)
        assert ctx.pending_slot is not None, (text, ctx.pending_slot)
        assert ctx.pending_slot["need"] == "url", (text, ctx.pending_slot)
    else:
        assert "could not tell" not in r["reply"].lower(), (text, r["reply"])
        assert r["intent"] == "web_open", (text, r)


def test_clarifying_url_slot_is_resolved():
    """After a clarifying question, supplying the site opens it."""
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "open")
    assert r["intent"] == "web_open"
    assert context.get(cid).pending_slot["need"] == "url"
    r = _say(cid, "github")
    assert r["intent"] == "web_open", (r["reply"], r)
    assert "github.com" in r["reply"], r["reply"]
    assert context.get(cid).pending_slot is None

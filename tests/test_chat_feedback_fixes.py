"""Fixes from a real chat on Windows (2026-11-21). Offline: no app is started, no key is pressed, no model is called.
* a coding request was answered "It is not found in the sources" from an unrelated notebook;
* "open WhatsApp" failed: the Microsoft Store app has no exe on the path;
* the screen look's object step crashed ("Boolean value of Tensor ... is ambiguous");
* "close Gmail" (a site in a browser tab) was refused, and "close gmail which you open in chrome tab" read as "open chrome";
* replies were spoken after any spoken command even with voice replies off; Chat had a second voice control."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adhyaksh import client, config
from adhyaksh.chat import context, identity, router
from adhyaksh.llm import base as llm
from adhyaksh.rag import answerer
from adhyaksh.result import Result
from adhyaksh.services import chat as chat_svc
from adhyaksh.tools import apps, windows
from tests.helpers import fresh_env


# ---- notebook answers do not swallow general requests ------------------------------------------------------------------
@pytest.mark.parametrize("said", [answerer.NOT_IN_SOURCES, "It is not found in the sources.",
                                  "The answer is not mentioned in the passages."])
def test_a_notebook_that_does_not_answer_gives_way(monkeypatch, said):
    fresh_env()
    hit = {"score": 0.9, "method": "tfidf", "filename": "PMDP.docx", "location": "Customer Portal", "text": "login"}
    monkeypatch.setattr(answerer.retriever, "retrieve", lambda q, notebook_id=None: [hit])
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "ask", lambda prompt, **k: Result.success(said))
    res = answerer.answer("write code for a simple login page in HTML")
    assert res.data["found"] is False and not res.data["sources"]


def test_a_real_notebook_answer_is_kept(monkeypatch):
    fresh_env()
    hit = {"score": 0.9, "method": "tfidf", "filename": "PMDP.docx", "location": "Customer Portal", "text": "login"}
    monkeypatch.setattr(answerer.retriever, "retrieve", lambda q, notebook_id=None: [hit])
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "ask", lambda prompt, **k: Result.success("Customers log in with email and OTP [1]."))
    res = answerer.answer("how do customers log in")
    assert res.data["found"] and "[1] PMDP.docx" in res.data["answer"]


def test_a_long_answer_that_mentions_a_missing_detail_still_counts():
    long = "The portal supports email login and OTP [1]. " * 6 + "Password rules are not found in the sources."
    assert not answerer.not_in_sources(long)


# ---- WhatsApp and other Microsoft Store apps ------------------------------------------------------------------------------
def test_store_app_ids_are_read_from_the_start_menu(monkeypatch):
    import json
    import subprocess
    rows = [{"Name": "WhatsApp", "AppID": "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"},
            {"Name": "Notepad", "AppID": "C:\\Windows\\notepad.exe"},  # a desktop app, not a Store id
            {"Name": "Bad", "AppID": "x & calc"}]
    monkeypatch.setattr(apps, "_START_APPS", None)
    monkeypatch.setattr(apps.os, "name", "nt")
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: subprocess.CompletedProcess(a, 0, json.dumps(rows), ""))
    assert apps.store_app_id("whatsapp") == "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"
    assert apps.store_app_id("notepad") is None and apps.store_app_id("bad") is None


def test_open_whatsapp_falls_back_to_the_store_app(monkeypatch):
    fresh_env()
    started = []

    def startfile(target):
        started.append(target)
        if target == "WhatsApp.exe":
            raise FileNotFoundError(target)
    monkeypatch.setattr(apps.os, "startfile", startfile, raising=False)
    monkeypatch.setattr(apps.os, "name", "nt")
    monkeypatch.setattr(apps, "store_app_id", lambda key: "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App")
    from adhyaksh.safety import verify
    monkeypatch.setattr(verify, "check", lambda action, target, res: res)
    res = apps.open_app("whatsapp")
    assert res.ok and started == ["WhatsApp.exe", "shell:AppsFolder\\5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"]


# ---- object step of "what's on my screen" --------------------------------------------------------------------------------
def test_classifier_reads_tensor_confidences(monkeypatch):
    torch = pytest.importorskip("torch")
    from adhyaksh.vision import detector

    class Probs:
        top5 = [3, 7]
        top5conf = torch.tensor([0.8, 0.1])

    class R:
        probs, names = Probs(), {3: "cup", 7: "laptop"}
    monkeypatch.setattr(detector, "_CLASSIFY_CACHE", {})
    monkeypatch.setattr(detector, "_load_classifier", lambda: (lambda img, imgsz=640, verbose=False: [R()]))
    import io

    from PIL import Image
    b = io.BytesIO()
    Image.new("RGB", (32, 32), (9, 9, 9)).save(b, "PNG")
    out = detector.classify(b.getvalue())
    assert [g["label"] for g in out] == ["cup", "laptop"] and abs(out[0]["confidence"] - 0.8) < 1e-6


# ---- closing a site's browser tab -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text, words", [
    ("https://mail.google.com/mail/u/0/#inbox this tab", ["gmail"]), ("Gmail which you open in chrome tabe", ["gmail"]),
    ("youtube.com", ["youtube"]), ("the bbc.co.uk tab", ["bbc"]), ("all tabs", []), ("this tab", []),
])
def test_tab_words(text, words):
    assert windows.tab_words(text) == words


@pytest.mark.parametrize("text, app", [
    ("close Gmail which you open in chrome tabe", "gmail"), ("close the youtube tab", "youtube"),
    ("close https://mail.google.com/mail/u/0/#inbox this tab", "gmail"), ("youtube tab band karo", "youtube"),
])
def test_closing_a_tab_is_never_read_as_opening_the_browser(text, app):
    r = router.understand(text)
    assert r is not None and r.intent == "app_close" and r.slots["app"] == app


@pytest.mark.parametrize("text", ["close this tab", "close all tabs", "close notes.txt"])
def test_no_tab_rule_without_a_site_name(text):
    r = router.understand(text)
    assert r is None or r.intent != "app_close" or r.slots.get("app") not in ("", "all", "this")


def _fake_windows(monkeypatch, wins):
    monkeypatch.setattr(windows, "_enum", lambda: wins)
    monkeypatch.setattr(windows.os, "name", "nt")


def test_find_tab_only_looks_at_browsers_and_never_at_the_console(monkeypatch):
    _fake_windows(monkeypatch, [
        {"hwnd": 1, "title": "ADHYAKSH - Gmail search - Google Chrome", "pid": 1, "process": "chrome.exe"},
        {"hwnd": 2, "title": "gmail notes.txt - Notepad", "pid": 2, "process": "notepad.exe"},
        {"hwnd": 3, "title": "Inbox (3) - me - Gmail - Google Chrome", "pid": 3, "process": "chrome.exe"},
    ])
    assert windows.find_tab("gmail")["hwnd"] == 3


class _User32:
    def __init__(self, foreground):
        self.fg, self.keys = foreground, []

    def GetForegroundWindow(self):
        return self.fg

    def keybd_event(self, vk, scan, flags, extra):
        self.keys.append((vk, flags))

    def IsIconic(self, hwnd):
        return False

    def SetForegroundWindow(self, hwnd):
        return True


def test_ctrl_w_only_when_the_browser_is_in_front(monkeypatch):
    fresh_env()
    _fake_windows(monkeypatch, [{"hwnd": 3, "title": "Inbox - Gmail - Google Chrome", "pid": 3, "process": "chrome.exe"}])
    from adhyaksh.safety import verify
    monkeypatch.setattr(verify, "check", lambda action, target, res: res)
    monkeypatch.setattr(windows.time, "sleep", lambda s: None)
    u = _User32(foreground=99)  # Windows refused to bring the browser to the front
    monkeypatch.setattr(windows, "_user32", lambda: u)
    res = windows.close_tab("gmail")
    assert not res.ok and (0x57, 0) not in u.keys, "no Ctrl+W may reach another window"
    u2 = _User32(foreground=3)
    monkeypatch.setattr(windows, "_user32", lambda: u2)
    assert windows.close_tab("gmail").ok and (0x11, 0) in u2.keys and (0x57, 0) in u2.keys


def test_close_gmail_closes_the_tab_when_gmail_is_not_an_app(monkeypatch):
    fresh_env()
    monkeypatch.setattr(apps.os, "name", "nt")
    monkeypatch.setattr(windows, "find_tab", lambda name: {"hwnd": 3})
    monkeypatch.setattr(windows, "close_tab", lambda name, ctx=None: Result.success({"title": "Gmail"}))
    assert apps.close_app("gmail").ok
    monkeypatch.setattr(windows, "find_tab", lambda name: None)
    res = apps.close_app("gmail")
    assert not res.ok and "allowed applications" in res.message


def test_tab_close_is_level_1_and_offered_to_the_agent_in_cowork_only():
    from adhyaksh.agent import native
    from adhyaksh.agent import registry
    from adhyaksh.safety import policy
    assert policy.LEVELS["tab_close"] == 1
    assert "tab_close" in [s["name"] for s in registry.schemas()]
    assert "tab_close" not in [s["name"] for s in native._tools_for("chat")]


# ---- voice replies: one switch, and no voice control on Chat ----------------------------------------------------------
CHAT = str(Path(__file__).resolve().parent.parent / "app_pages" / "chat.py")


@pytest.fixture
def chat(monkeypatch):
    fresh_env()
    identity.save_name("Tester")
    monkeypatch.setattr(client, "available", lambda: False)
    calls = []
    monkeypatch.setattr(chat_svc, "bridge_voice_input", lambda **kw: calls.append(kw))
    return calls


def test_chat_has_no_voice_controls(chat):
    at = AppTest.from_file(CHAT, default_timeout=60)
    at.session_state["cid"] = context.new_conversation()
    at.run()
    assert not any(e.label == "Voice controls" for e in at.expander)
    assert chat == [], "with voice replies off, nothing voice-related is on the page"


def test_with_voice_replies_on_chat_only_speaks_and_never_listens(chat):
    config.set_value("voice_reply", "true")
    config.set_value("voice_handsfree", "true")
    config.set_value("voice_wake_word", "true")
    cid = context.new_conversation()
    at = AppTest.from_file(CHAT, default_timeout=60)
    at.session_state["cid"] = cid
    at.run()
    context.save_message(cid, "user", "hello")
    context.save_message(cid, "assistant", "Hello, Tester.")
    at.run()
    assert chat[-1]["speak_text"] == "Hello, Tester."
    assert chat[-1]["handsfree_default"] is False and chat[-1]["wake_default"] is False


def test_a_spoken_command_is_not_read_out_when_voice_replies_are_off(chat, monkeypatch):
    cid = context.new_conversation()

    def fake(text, c, voice=False, mode="cowork", attachments=None, stream=False):
        context.save_message(c, "user", text)
        context.save_message(c, "assistant", "Done.")
        return Result.success({"reply": "Done."})
    monkeypatch.setattr(chat_svc, "engine_handle_message", fake)
    at = AppTest.from_file(CHAT, default_timeout=60)
    at.session_state["cid"] = cid
    at.run()
    at.chat_input(key="composer").set_value("open notepad").run()
    assert chat == []


def test_settings_switch_saves_at_once():
    fresh_env()
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app_pages" / "settings.py"), default_timeout=60).run()
    at.toggle(key="voice_reply_toggle").set_value(True).run()
    assert config.get_bool("voice_reply")
    at.toggle(key="voice_reply_toggle").set_value(False).run()
    assert not config.get_bool("voice_reply")

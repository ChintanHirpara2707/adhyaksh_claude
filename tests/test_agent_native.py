"""Native tool-calling agent: loop, safety gateway, confirmation, honesty guard and the three wire formats.

No real model or network is used: llm.chat is replaced by a scripted fake, and requests.request (used by net.py) by a recorder."""
import json
import os

import pytest

from adhyaksh import config
from adhyaksh.agent import native, registry
from adhyaksh.chat import context, engine
from adhyaksh.llm import base as llm
from adhyaksh.llm import gemini, groq, ollama
from adhyaksh.result import Result
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"


def _setup(monkeypatch, script):
    """Fresh workspace, local provider selected, llm.chat scripted. Returns (workspace, calls made to the model)."""
    base = fresh_env()
    ws = base / "ws"
    ws.mkdir()
    config.set_value("allowed_folders", json.dumps([str(ws)]))
    config.set_value("default_work_folder", str(ws))
    config.set_value("llm_provider", "ollama")  # local: no consent needed
    seen = []
    steps = iter(script)

    def fake_chat(messages, tools=None, timeout=25.0, max_tokens=1024):
        seen.append({"messages": [dict(m) for m in messages], "tools": [t["name"] for t in (tools or [])]})
        try:
            out = next(steps)
        except StopIteration:
            out = {"text": "Done.", "tool_calls": []}
        return out if isinstance(out, Result) else Result.success(out)

    monkeypatch.setattr(llm, "chat", fake_chat)
    return ws, seen


def call(name, **arguments):
    return {"text": "", "tool_calls": [{"id": "c1", "name": name, "arguments": arguments}]}


def test_agent_creates_file_in_default_work_folder_through_gateway(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("file_create", path="plan.txt", content="hello"),
                                    {"text": "I have created plan.txt in your work folder.", "tool_calls": []}])
    cid = context.new_conversation()
    r = engine.handle_message("make a file plan.txt with hello", cid).data
    assert r["intent"] == "agent" and "created plan.txt" in r["reply"]
    assert (ws / "plan.txt").read_text(encoding="utf-8") == "hello"  # relative path resolved against default_work_folder
    assert "file_create" in seen[0]["tools"] and str(ws) in seen[0]["messages"][0]["content"]
    assert seen[1]["messages"][-1]["role"] == "tool" and '"status": "ok"' in seen[1]["messages"][-1]["content"]
    from adhyaksh import db
    assert db.query_one("SELECT COUNT(*) AS n FROM audit_log WHERE action='file_create'")["n"] == 1


def test_agent_cannot_write_outside_allowed_folders(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("file_create", path="C:/Windows/evil.txt", content="x"),
                                    {"text": "I have created the file.", "tool_calls": []}])
    r = engine.handle_message("create C:/Windows/evil.txt", context.new_conversation()).data
    assert "could not do that" in r["reply"].lower()  # the false claim was replaced by the real error
    assert '"status": "error"' in seen[1]["messages"][-1]["content"]


def test_model_claiming_an_action_without_any_tool_is_corrected(monkeypatch):
    _setup(monkeypatch, [{"text": "Done! I have deleted report.txt and opened Chrome for you.", "tool_calls": []}])
    r = engine.handle_message("delete report.txt and open chrome", context.new_conversation()).data
    assert "have not carried out any action" in r["reply"] and "deleted" not in r["reply"]
    assert native.guard_claims("मैंने फाइल बना दी है", []) != "मैंने फाइल बना दी है"
    assert native.guard_claims("file bana di hai", []).startswith("I have not")
    assert native.guard_claims("ફાઇલ બનાવી દીધી છે", []).startswith("I have not")
    ok = [{"status": "ok"}]
    assert native.guard_claims("I have created notes.txt.", ok) == "I have created notes.txt."
    assert native.guard_claims("The capital of France is Paris.", []) == "The capital of France is Paris."


def test_app_close_runs_without_confirmation(monkeypatch):
    _setup(monkeypatch, [call("app_close", app="notepad"), {"text": "Notepad was not running.", "tool_calls": []}])
    from adhyaksh.tools import apps
    ran = []
    import psutil
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: ran.append("iter") or [])
    cid = context.new_conversation()
    r = engine.handle_message("close notepad", cid).data
    assert r["intent"] != "agent_confirm" and ran
    res = apps.close_app("notepad")
    assert res.error_code != "E_NEEDS_CONFIRM" and "not running" in res.message


def test_confirmation_yes_runs_the_tool_and_finishes(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("file_delete", path="old.txt"), {"text": "I have deleted old.txt.", "tool_calls": []}])
    (ws / "old.txt").write_text("x", encoding="utf-8")
    cid = context.new_conversation()
    r = engine.handle_message("delete old.txt", cid).data
    assert r["intent"] == "agent_confirm" and (ws / "old.txt").exists()
    r2 = engine.handle_message("yes", cid).data
    assert not (ws / "old.txt").exists() and "deleted old.txt" in r2["reply"]


def test_chat_mode_hides_action_tools(monkeypatch):
    _, seen = _setup(monkeypatch, [{"text": "Please switch to Cowork mode for that.", "tool_calls": []}])
    engine.handle_message("open notepad", context.new_conversation(), mode="chat")
    assert "app_open" not in seen[0]["tools"] and "file_delete" not in seen[0]["tools"] and "memory_save" in seen[0]["tools"]
    assert "Chat mode is active" in seen[0]["messages"][0]["content"]


def test_unknown_tool_and_ui_hints(monkeypatch):
    _, seen = _setup(monkeypatch, [call("format_disk", drive="C"), call("voice_control", action="stop"),
                                   {"text": "Listening is off.", "tool_calls": []}])
    r = engine.handle_message("stop listening", context.new_conversation()).data
    assert r["voice_cmd"]["action"] == "stop" and r["reply"] == "Listening is off."
    assert "not available" in seen[1]["messages"][-1]["content"]


def test_model_unreachable_falls_back_to_offline_rules(monkeypatch):
    _setup(monkeypatch, [Result.failure("E_TIMEOUT", "The language model did not respond: timeout.")])
    r = engine.handle_message("what is 6 * 7", context.new_conversation()).data
    assert r["intent"] == "math" and "42" in r["reply"]


def test_agent_off_setting_uses_rules(monkeypatch):
    _, seen = _setup(monkeypatch, [])
    config.set_value("agent_mode", "off")
    r = engine.handle_message("what is 6 * 7", context.new_conversation()).data
    assert r["intent"] == "math" and not seen


def test_cloud_agent_needs_consent(monkeypatch):
    fresh_env()
    config.set_value("llm_provider", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    assert not native.available()  # no consent yet
    config.set_value("cloud_consent", "true")
    assert native.available()


# ---------------------------------------------------------------------------------- wire formats
class _Resp:
    status_code = 200

    def __init__(self, data):
        self._d = data

    def raise_for_status(self):
        return None

    def json(self):
        return self._d


MSGS = [{"role": "system", "content": "sys"}, {"role": "user", "content": "create a.txt"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "file_create", "arguments": {"path": "a.txt"}}]},
        {"role": "tool", "tool_call_id": "c1", "name": "file_create", "content": "{\"status\": \"ok\"}"}]
TOOLS = [{"name": "file_create", "description": "Create a file", "parameters": {"type": "object", "properties": {"path": {"type": "string"}},
                                                                                 "required": ["path"]}}]


def test_groq_wire_format(monkeypatch):
    fresh_env()
    sent = {}
    import requests

    def post(method, url, timeout=None, headers=None, json=None):
        sent.update(url=url, json=json, headers=headers)
        return _Resp({"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "x9", "type": "function", "function": {"name": "file_read", "arguments": "{\"path\": \"a.txt\"}"}}]}}]})
    monkeypatch.setattr(requests, "request", post)
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real")
    out = groq.GroqProvider().chat(MSGS, TOOLS).data
    assert out["tool_calls"] == [{"id": "x9", "name": "file_read", "arguments": {"path": "a.txt"}}]
    j = sent["json"]
    assert j["tools"][0] == {"type": "function", "function": TOOLS[0]} and j["tool_choice"] == "auto"
    assert j["messages"][2]["tool_calls"][0]["function"]["arguments"] == "{\"path\": \"a.txt\"}"
    assert j["messages"][3] == {"role": "tool", "tool_call_id": "c1", "content": "{\"status\": \"ok\"}"}


def test_gemini_wire_format(monkeypatch):
    fresh_env()
    sent = {}
    import requests

    def post(method, url, timeout=None, headers=None, json=None):
        sent.update(url=url, json=json)
        return _Resp({"candidates": [{"content": {"parts": [{"text": "ok "}, {"functionCall": {"name": "file_read", "args": {"path": "a.txt"}}}]}}]})
    monkeypatch.setattr(requests, "request", post)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")
    out = gemini.GeminiProvider().chat(MSGS, TOOLS).data
    assert out["text"] == "ok " and out["tool_calls"][0]["name"] == "file_read" and out["tool_calls"][0]["arguments"] == {"path": "a.txt"}
    j = sent["json"]
    assert j["systemInstruction"]["parts"][0]["text"] == "sys"
    decl = j["tools"][0]["functionDeclarations"][0]
    assert decl["parameters"]["type"] == "OBJECT" and decl["parameters"]["properties"]["path"]["type"] == "STRING"
    assert j["contents"][1]["role"] == "model" and j["contents"][1]["parts"][0]["functionCall"]["name"] == "file_create"
    assert j["contents"][2]["parts"][0]["functionResponse"]["name"] == "file_create"
    assert "test-key-not-real" not in sent["url"]  # the key travels in a header, never in the URL


def test_ollama_wire_format_and_errors(monkeypatch):
    fresh_env()
    sent = {}
    import requests

    def post(method, url, timeout=None, headers=None, json=None):
        sent.update(url=url, json=json)
        return _Resp({"message": {"content": "", "tool_calls": [{"function": {"name": "get_time", "arguments": {}}}]}})
    monkeypatch.setattr(requests, "request", post)
    out = ollama.OllamaProvider().chat(MSGS, TOOLS).data
    assert out["tool_calls"][0]["name"] == "get_time" and sent["url"].startswith("http://127.0.0.1:11434/api/chat")
    assert sent["json"]["messages"][3]["role"] == "tool" and sent["json"]["stream"] is False

    def down(*a, **k):
        raise requests.ConnectionError("refused")
    monkeypatch.setattr(requests, "request", down)
    monkeypatch.setattr("adhyaksh.net.time.sleep", lambda s: None)
    res = ollama.OllamaProvider().chat(MSGS, TOOLS)
    assert not res.ok and "could not connect" in res.message


def test_every_registered_tool_has_an_object_schema():
    for s in registry.schemas():
        assert s["parameters"]["type"] == "object" and isinstance(s["parameters"].get("properties", {}), dict), s["name"]

"""Phase 2a: verification and error recovery. Post-condition checks at the safety gateway, retryable/hint on
failures, loop guards (identical failed call, per-tool limit, destructive actions never retried, time budget) and
the ask_user pause. The model is scripted; no network is used."""
import json
import time

import pytest

from adhyaksh import config
from adhyaksh.agent import native, registry
from adhyaksh.chat import context, engine
from adhyaksh.llm import base as llm
from adhyaksh.result import E_ACTION_FAILED, E_FILE_NOT_FOUND, E_UNVERIFIED, Result
from adhyaksh.safety import policy, verify
from tests.helpers import fresh_env


def call(name, **arguments):
    return {"text": "", "tool_calls": [{"id": "c1", "name": name, "arguments": arguments}]}


def _setup(monkeypatch, script):
    base = fresh_env()
    ws = base / "ws"
    ws.mkdir()
    config.set_value("allowed_folders", json.dumps([str(ws)]))
    config.set_value("default_work_folder", str(ws))
    config.set_value("llm_provider", "ollama")
    config.set_value("routing", "llm_first")
    seen, steps = [], iter(script)

    def fake_chat(messages, tools=None, timeout=25.0, max_tokens=1024):
        seen.append([dict(m) for m in messages])
        try:
            out = next(steps)
        except StopIteration:
            out = {"text": "Done.", "tool_calls": []}
        return out if isinstance(out, Result) else Result.success(out)
    monkeypatch.setattr(llm, "chat", fake_chat)
    return ws, seen


def _last_tool_payload(seen):
    msg = [m for m in seen[-1] if m["role"] == "tool"][-1]
    return json.loads(msg["content"].split("\n(The block above")[0])


# ---- post-condition checks at the gateway ------------------------------------------------------------------
def test_success_is_verified_on_the_real_file(tmp_path):
    fresh_env()
    f = tmp_path / "a.txt"
    res = policy.run_guarded("file_create", "a.txt", lambda: (f.write_text("x"), Result.success({"path": str(f)}))[1])
    assert res.ok and res.data["verified"] is True


def test_a_claimed_success_that_did_not_happen_is_caught(tmp_path):
    fresh_env()
    res = policy.run_guarded("file_create", "ghost.txt", lambda: Result.success({"path": str(tmp_path / "ghost.txt")}))
    assert not res.ok and res.error_code == E_UNVERIFIED and "ghost.txt does not exist" in res.message
    assert res.data["retryable"] is True


def test_delete_is_verified_gone(tmp_path):
    fresh_env()
    f = tmp_path / "old.txt"
    f.write_text("x")
    still_there = verify.check("file_delete", "old.txt", Result.success({"path": str(f)}))
    assert not still_there.ok and "still there" in still_there.message
    f.unlink()
    assert verify.check("file_delete", "old.txt", Result.success({"path": str(f)})).data["verified"] is True


def test_unknown_effects_are_left_as_cannot_tell():
    res = verify.check("app_open", "notepad", Result.success({"app": "notepad"}))  # shell launch: no pid to check
    assert res.ok and res.data["verified"] is None
    assert verify.check("perf_stats", "system", Result.success({"cpu": 1})).data == {"cpu": 1}  # no check registered


def test_a_check_that_crashes_never_breaks_the_action(monkeypatch):
    monkeypatch.setitem(verify._CHECKS, "reminder_add", lambda t, d: 1 / 0)
    assert verify.check("reminder_add", "x", Result.success({"id": 1})).ok


# ---- diagnosis -----------------------------------------------------------------------------------------------
def test_missing_file_gets_similar_names(tmp_path):
    for n in ("notes.txt", "note.txt", "budget.xlsx"):
        (tmp_path / n).write_text("x")
    res = verify.explain("file_read", "notess.txt", 0, Result.failure(E_FILE_NOT_FOUND, "File not found."), base=tmp_path)
    assert res.data["retryable"] is True and "notes.txt" in res.data["hint"]
    none = verify.explain("file_read", "zzz.pdf", 0, Result.failure(E_FILE_NOT_FOUND, "File not found."), base=tmp_path)
    assert none.data["retryable"] is False


def test_destructive_and_blocked_failures_are_never_retryable():
    assert verify.explain("file_delete", "x.txt", 2, Result.failure("E_TIMEOUT", "slow")).data["retryable"] is False
    assert verify.explain("app_open", "regedit", 1, Result.failure("E_BLOCKED", "not allowed")).data["retryable"] is False
    assert verify.explain("app_close", "chrome", 1, Result.failure(E_ACTION_FAILED, "chrome is not running.")).data == \
        {"retryable": False, "hint": "it is already closed"}


def test_gateway_failures_carry_retryable_and_hint():
    fresh_env()
    res = policy.run_guarded("perf_stats", "system", lambda: Result.failure("E_TIMEOUT", "took too long"))
    assert res.data["retryable"] is True


# ---- the agent loop ---------------------------------------------------------------------------------------------
def test_the_model_sees_the_hint_and_corrects_itself(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("file_read", path="notess.txt"), call("file_read", path="notes.txt"),
                                    {"text": "notes.txt says hello.", "tool_calls": []}])
    (ws / "notes.txt").write_text("hello", encoding="utf-8")
    r = engine.handle_message("read my notess file", context.new_conversation()).data
    assert r["reply"] == "notes.txt says hello."
    first_error = json.loads([m for m in seen[1] if m["role"] == "tool"][-1]["content"].split("\n(The block above")[0])
    assert first_error["retryable"] is True and "notes.txt" in first_error["hint"]


def test_an_identical_failed_call_is_refused_then_the_loop_stops(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("file_read", path="missing.txt")] * 5)
    r = native.run("read missing.txt", context.new_conversation())
    assert "kept failing" in r["reply"] and len(seen) == 3
    assert "already failed" in _last_tool_payload(seen)["error"]
    assert [s["status"] for s in r["steps"]] == ["error", "skipped", "skipped"]


def test_a_failed_destructive_action_is_not_retried(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("file_delete", path="a.txt"), call("file_delete", path="b.txt"),
                                    {"text": "I could not delete them.", "tool_calls": []}])
    monkeypatch.setattr(registry.files, "delete", lambda *a, **k: Result.failure(E_ACTION_FAILED, "disk error"))
    r = native.run("delete a.txt and b.txt", context.new_conversation())
    assert r["steps"][1]["status"] == "skipped" and "not retried automatically" in _last_tool_payload(seen)["error"]


def test_time_budget_stops_the_loop(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("get_time")] * 10)
    monkeypatch.setattr(native, "TIME_BUDGET", -1.0)  # already exceeded (the Windows clock ticks in about 15 ms steps)
    r = native.run("what time", context.new_conversation())
    assert "taking too long" in r["reply"] and not seen


def test_ask_user_pauses_and_the_answer_resumes(monkeypatch):
    ws, seen = _setup(monkeypatch, [
        call("ask_user", question="Which file?", options=["notes.txt", "notes2.txt"]),
        call("file_read", path="notes2.txt"), {"text": "notes2.txt says hi.", "tool_calls": []}])
    (ws / "notes2.txt").write_text("hi", encoding="utf-8")
    cid = context.new_conversation()
    r = engine.handle_message("read my notes", cid).data
    assert r["intent"] == "agent_ask" and r["reply"].startswith("Which file?") and "2. notes2.txt" in r["reply"]
    r = engine.handle_message("the second one", cid).data
    assert r["reply"] == "notes2.txt says hi."
    answer = [m for m in seen[1] if m["role"] == "tool" and m["name"] == "ask_user"][-1]["content"]
    assert '"answer": "the second one"' in answer


def test_ask_user_can_be_dropped(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("ask_user", question="Which file?")])
    cid = context.new_conversation()
    engine.handle_message("read my notes", cid)
    r = engine.handle_message("cancel", cid).data
    assert r["action"] == "cancel" and len(seen) == 1 and not native._PENDING_ASK


def test_verified_flag_reaches_the_steps(monkeypatch):
    ws, seen = _setup(monkeypatch, [call("file_create", path="made.txt", content="x"), {"text": "Created.", "tool_calls": []}])
    r = native.run("create made.txt", context.new_conversation())
    assert r["steps"][0]["status"] == "ok" and r["steps"][0]["verified"] is True and (ws / "made.txt").exists()

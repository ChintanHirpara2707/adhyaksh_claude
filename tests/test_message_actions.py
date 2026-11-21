"""Phase 4e: message actions (copy, regenerate, edit and resend) and the step line showing which tool ran.
Offline: timestamps and audit rows are written directly; the engine and model are faked where needed."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adhyaksh import client, db
from adhyaksh.chat import context, identity
from adhyaksh.llm import base as llm
from adhyaksh.llm import cache
from adhyaksh.result import Result
from adhyaksh.safety import audit
from adhyaksh.services import chat as svc
from tests.helpers import fresh_env

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "chat.py")


def _msg(cid, role, text, ts):
    return db.execute("INSERT INTO messages(conversation_id, role, content, created_at) VALUES(?,?,?,?)",
                      (cid, role, text, ts))


def _audit(action, target, result, ts, level=1, user_text=""):
    audit.record(user_text=user_text, intent="", action=action, target=target, level=level, confirmed="none",
                 result=result, ts=ts)


@pytest.fixture
def env(monkeypatch):
    fresh_env()
    identity.save_name("Tester")
    monkeypatch.setattr(client, "available", lambda: False)
    monkeypatch.setattr(svc, "bridge_voice_input", lambda **kw: None)


# ---- which tool ran, per reply ------------------------------------------------------------------------------------------
def test_steps_belong_to_the_reply_of_their_turn(env):
    cid = context.new_conversation()
    _msg(cid, "user", "hello", "2026-11-21T10:00:00+00:00")
    a1 = _msg(cid, "assistant", "Hello.", "2026-11-21T10:00:01+00:00")
    _msg(cid, "user", "create notes.txt", "2026-11-21T10:01:00+00:00")
    _audit("file_create", "C:/w/notes.txt", "ok", "2026-11-21T10:01:01+00:00")
    a2 = _msg(cid, "assistant", "Created notes.txt.", "2026-11-21T10:01:01+00:00")
    _audit("app_open", "notepad", "ok", "2026-11-21T10:05:00+00:00")  # between turns (another window): no reply
    steps = svc.turn_steps(context.history(cid, 50))
    assert a1 not in steps and [s["action"] for s in steps[a2]] == ["file create"]
    assert steps[a2][0]["outcome"] == "done" and steps[a2][0]["state"] == "complete"


def test_a_confirmed_action_belongs_to_the_reply_after_the_confirmation(env):
    cid = context.new_conversation()
    _msg(cid, "user", "delete notes.txt", "2026-11-21T10:00:00+00:00")
    ask = _msg(cid, "assistant", "Delete notes.txt? Confirm or cancel.", "2026-11-21T10:00:01+00:00")
    _audit("file_delete", "C:/w/notes.txt", "failed: E_NOT_FOUND", "2026-11-21T10:00:30+00:00", level=2)
    done = _msg(cid, "assistant", "I could not do that: not found.", "2026-11-21T10:00:30+00:00")
    steps = svc.turn_steps(context.history(cid, 50))
    assert ask not in steps and steps[done][0]["state"] == "error" and steps[done][0]["outcome"] == "failed"


def test_a_tool_from_another_conversation_in_the_same_second_is_not_shown(env):
    other = context.new_conversation()
    cid = context.new_conversation()
    _msg(cid, "user", "hello", "2026-11-21T10:00:00+00:00")
    _msg(other, "user", "show system status", "2026-11-21T10:00:00+00:00")
    _audit("system_status", "system", "ok", "2026-11-21T10:00:00+00:00", level=0, user_text="show system status")
    hi = _msg(cid, "assistant", "Hello.", "2026-11-21T10:00:00+00:00")
    assert hi not in svc.turn_steps(context.history(cid, 50))


def test_turns_within_one_second_each_get_their_own_tool(env):
    cid = context.new_conversation()
    t = "2026-11-21T10:00:00+00:00"
    _msg(cid, "user", "hello", t)
    hi = _msg(cid, "assistant", "Hello.", t)
    _msg(cid, "user", "create notes.txt", t)
    _audit("file_create", "C:/w/notes.txt", "ok", t, user_text="create notes.txt")
    done = _msg(cid, "assistant", "Created.", t)
    steps = svc.turn_steps(context.history(cid, 50))
    assert hi not in steps and [s["action"] for s in steps[done]] == ["file create"]


def test_a_typed_yes_still_shows_the_confirmed_action(env):
    cid = context.new_conversation()
    _msg(cid, "user", "delete notes.txt", "2026-11-21T10:00:00+00:00")
    _msg(cid, "assistant", "Delete notes.txt? Confirm or cancel.", "2026-11-21T10:00:01+00:00")
    _msg(cid, "user", "haan", "2026-11-21T10:00:05+00:00")
    _audit("file_delete", "C:/w/notes.txt", "ok", "2026-11-21T10:00:06+00:00", level=2, user_text="delete notes.txt")
    done = _msg(cid, "assistant", "Deleted notes.txt.", "2026-11-21T10:00:06+00:00")
    assert svc.turn_steps(context.history(cid, 50))[done][0]["action"] == "file delete"


def test_one_step_of_a_multi_step_message_is_shown(env):
    cid = context.new_conversation()
    _msg(cid, "user", "create plan.txt and then open notepad", "2026-11-21T10:00:00+00:00")
    _audit("file_create", "C:/w/plan.txt", "ok", "2026-11-21T10:00:01+00:00", user_text="create plan.txt")
    _audit("app_open", "notepad", "ok", "2026-11-21T10:00:01+00:00", user_text="open notepad")
    r = _msg(cid, "assistant", "Done both.", "2026-11-21T10:00:02+00:00")
    assert [s["action"] for s in svc.turn_steps(context.history(cid, 50))[r]] == ["file create", "app open"]


# ---- regenerate ---------------------------------------------------------------------------------------------------------
def test_regenerate_only_without_tools_and_only_the_last_reply(env):
    cid = context.new_conversation()
    _msg(cid, "user", "explain photosynthesis", "2026-11-21T10:00:00+00:00")
    _msg(cid, "assistant", "Plants make sugar.", "2026-11-21T10:00:02+00:00")
    assert svc.can_regenerate(cid)
    _msg(cid, "user", "create notes.txt", "2026-11-21T10:01:00+00:00")
    _audit("file_create", "C:/w/notes.txt", "ok", "2026-11-21T10:01:01+00:00")
    _msg(cid, "assistant", "Created notes.txt.", "2026-11-21T10:01:01+00:00")
    assert not svc.can_regenerate(cid), "asking again must never repeat an action"
    res = svc.regenerate(cid)
    assert not res.ok and len(context.history(cid, 50)) == 4


def test_regenerate_replaces_the_turn_and_skips_the_cache(env, monkeypatch):
    cid = context.new_conversation()
    _msg(cid, "user", "explain photosynthesis", "2026-11-21T10:00:00+00:00")
    _msg(cid, "assistant", "Old answer.", "2026-11-21T10:00:02+00:00")
    seen = {}

    def fake(text, conversation_id, mode="cowork", stream=False, **kw):
        seen["fresh"] = llm._FRESH.get()
        context.save_message(conversation_id, "user", text)
        context.save_message(conversation_id, "assistant", "New answer.")
        return Result.success({"reply": "New answer."})
    monkeypatch.setattr(svc.engine, "handle_message", fake)
    assert svc.regenerate(cid).ok and seen["fresh"] is True
    assert [m["content"] for m in context.history(cid, 50)] == ["explain photosynthesis", "New answer."]


class _Fake(llm.Provider):
    name = "ollama"
    calls = 0

    def _call(self, prompt, timeout):
        _Fake.calls += 1
        return f"answer {_Fake.calls}"

    def _stream(self, prompt, timeout):
        _Fake.calls += 1
        yield f"streamed {_Fake.calls}"


def test_fresh_skips_reading_the_cache_but_still_writes_it(env):
    cache.clear()
    p = _Fake()
    assert p.complete("q").data == "answer 1" and p.complete("q").data == "answer 1"  # cached
    with llm.fresh():
        assert p.complete("q").data == "answer 2"
    assert p.complete("q").data == "answer 2"  # the new answer replaced the cached one
    assert list(p.stream("s")) == ["streamed 3"] and list(p.stream("s")) == ["streamed 3"]
    assert list(p.stream("s", use_cache=False)) == ["streamed 4"]


def test_stream_ask_takes_the_fresh_choice_when_called(env, monkeypatch):
    config_seen = {}
    monkeypatch.setattr(llm, "is_local", lambda: True)

    class P:
        def stream(self, prompt, timeout, max_tokens, use_cache=True):
            config_seen["use_cache"] = use_cache
            return iter(["x"])
    monkeypatch.setattr(llm, "get_provider", lambda: P())
    with llm.fresh():
        llm.stream_ask("q")
    assert config_seen["use_cache"] is False
    llm.stream_ask("q")
    assert config_seen["use_cache"] is True


# ---- edit and resend ----------------------------------------------------------------------------------------------------
@pytest.fixture
def sent(env, monkeypatch):
    calls = []

    def fake(text, cid, voice=False, mode="cowork", attachments=None, stream=False):
        calls.append(text)
        context.save_message(cid, "user", text)
        context.save_message(cid, "assistant", f"reply to {text}")
        return Result.success({"reply": "ok"})
    monkeypatch.setattr(svc, "engine_handle_message", fake)
    return calls


def test_edit_replaces_a_turn_where_no_tool_ran(sent):
    cid = context.new_conversation()
    u = _msg(cid, "user", "what is 12 * 8", "2026-11-21T10:00:00+00:00")
    _msg(cid, "assistant", "96", "2026-11-21T10:00:01+00:00")
    assert svc.edit_and_resend(cid, u, "what is 12 * 7").ok
    assert [m["content"] for m in context.history(cid, 50)] == ["what is 12 * 7", "reply to what is 12 * 7"]


def test_edit_keeps_a_turn_where_a_tool_ran(sent):
    cid = context.new_conversation()
    u = _msg(cid, "user", "create note.txt", "2026-11-21T10:00:00+00:00")
    _audit("file_create", "C:/w/note.txt", "ok", "2026-11-21T10:00:01+00:00")
    _msg(cid, "assistant", "Created note.txt.", "2026-11-21T10:00:01+00:00")
    assert svc.edit_and_resend(cid, u, "create notes.txt").ok
    assert [m["content"] for m in context.history(cid, 50)][:2] == ["create note.txt", "Created note.txt."]
    assert len(context.history(cid, 50)) == 4


def test_only_the_last_message_can_be_edited_and_not_to_empty(sent):
    cid = context.new_conversation()
    u1 = _msg(cid, "user", "hello", "2026-11-21T10:00:00+00:00")
    _msg(cid, "assistant", "Hello.", "2026-11-21T10:00:01+00:00")
    u2 = _msg(cid, "user", "bye", "2026-11-21T10:00:02+00:00")
    assert not svc.edit_and_resend(cid, u1, "hi").ok
    assert not svc.edit_and_resend(cid, u2, "   ").ok and not sent


# ---- the page ------------------------------------------------------------------------------------------------------------
def _page(cid):
    at = AppTest.from_file(PAGE, default_timeout=60)
    at.session_state["cid"] = cid
    return at.run()


def test_page_shows_the_step_line_and_the_actions(env):
    cid = context.new_conversation()
    _msg(cid, "user", "create notes.txt", "2026-11-21T10:00:00+00:00")
    _audit("file_create", "C:/w/notes.txt", "ok", "2026-11-21T10:00:01+00:00")
    r = _msg(cid, "assistant", "Created notes.txt.", "2026-11-21T10:00:01+00:00")
    at = _page(cid)
    assert not at.exception
    assert [s.label for s in at.status] == ["File create: done"]
    keys = {b.key for b in at.button}
    assert f"regen_{r}" not in keys, "no Regenerate after an action"
    assert any(k and k.startswith("editbtn_") for k in keys) and f"wrong_{r}" in keys


def test_page_regenerate_runs_again(env, monkeypatch):
    cid = context.new_conversation()
    _msg(cid, "user", "explain photosynthesis", "2026-11-21T10:00:00+00:00")
    r = _msg(cid, "assistant", "Old answer.", "2026-11-21T10:00:02+00:00")
    asked = []
    monkeypatch.setattr(svc, "regenerate", lambda c, mode="cowork": asked.append(c) or Result.success({"reply": "x"}))
    at = _page(cid)
    at.button(key=f"regen_{r}").click().run()
    assert asked == [cid] and not at.exception


def test_page_edit_and_send(env, monkeypatch):
    cid = context.new_conversation()
    u = _msg(cid, "user", "what is 12 * 8", "2026-11-21T10:00:00+00:00")
    _msg(cid, "assistant", "96", "2026-11-21T10:00:01+00:00")
    edits = []
    monkeypatch.setattr(svc, "edit_and_resend",
                        lambda c, mid, text, mode="cowork": edits.append((mid, text)) or Result.success({"reply": "x"}))
    at = _page(cid)
    at.button(key=f"editbtn_{u}").click().run()
    at.text_area[0].input("what is 12 * 7")
    next(b for b in at.button if b.label == "Send").click().run()
    assert edits == [(u, "what is 12 * 7")] and not at.exception

"""Phase 3a-1: the event bus, and confirmations that survive a restart of the background engine (but never revive
a confirmation the user walked away from)."""
import queue

import pytest

from adhyaksh import events
from adhyaksh.chat import context, engine
from adhyaksh.memory import store
from adhyaksh.result import E_NEEDS_CONFIRM, Result
from adhyaksh.safety import confirm, policy
from tests.helpers import fresh_env


@pytest.fixture(autouse=True)
def _env():
    fresh_env()
    events.reset()
    yield
    events.reset()


def _restart():
    """What a restart loses: every conversation context held in memory."""
    context._CTX.clear()


# ---- event bus ---------------------------------------------------------------------------------------------------
def test_publish_reaches_every_listener_and_never_blocks():
    a, b = events.subscribe(), events.subscribe()
    events.publish("notice", text="battery low")
    assert a.get_nowait()["text"] == "battery low" and b.get_nowait()["type"] == "notice"
    for i in range(events._MAX_QUEUE + 50):  # a listener that stopped reading
        events.publish("notice", n=i)
    assert a.qsize() == events._MAX_QUEUE and a.queue[-1]["n"] == events._MAX_QUEUE + 49  # newest kept
    events.unsubscribe(b)
    events.publish("notice", text="x")
    assert b.qsize() == events._MAX_QUEUE  # unsubscribed: nothing more arrives


def test_state_changes_are_published_once():
    q = events.subscribe()
    events.set_state("listening")
    events.set_state("listening")
    events.set_state("nonsense")
    assert [e["state"] for e in list(q.queue)] == ["listening"] and events.current_state()["state"] == "listening"


def test_a_message_goes_thinking_executing_idle_and_publishes_the_reply():
    q = events.subscribe()
    policy.run_guarded("file_create", "x", lambda: Result.success({}))  # level 1: executing
    engine.handle_message("hello", context.new_conversation())
    seen = [(e["type"], e.get("state")) for e in list(q.queue)]
    assert ("state", "executing") in seen and ("state", "thinking") in seen and seen[-1] == ("reply", None)
    assert ("state", "idle") in seen and events.current_state()["state"] == "idle"


# ---- persistent tokens ----------------------------------------------------------------------------------------------
def test_tokens_survive_a_new_store_instance_and_stay_one_time():
    first = confirm.DbConfirmationStore()
    p = first.create("file_delete", "a.txt", "delete a.txt", "file_delete")
    second = confirm.DbConfirmationStore()  # a restarted process
    assert second.peek(p.token).target == "a.txt"
    assert second.consume(p.token, "file_delete", "b.txt") is None  # wrong target: refused, still pending
    assert second.consume(p.token, "file_delete", "a.txt") is not None
    assert second.consume(p.token, "file_delete", "a.txt") is None  # one time only


def test_tokens_expire_on_wall_clock_time():
    now = [1000.0]
    s = confirm.DbConfirmationStore(ttl=60, clock=lambda: now[0])
    p = s.create("process_kill", "zoom.exe")
    now[0] += 61
    assert s.peek(p.token) is None and s.consume(p.token, "process_kill", "zoom.exe") is None


def test_the_gateway_uses_the_persistent_store():
    assert isinstance(policy.STORE, confirm.DbConfirmationStore)
    res = policy.run_guarded("process_kill", "zoom.exe", lambda: Result.success({}))
    assert res.error_code == E_NEEDS_CONFIRM and confirm.DbConfirmationStore().peek(res.data["token"])


# ---- replay after a restart --------------------------------------------------------------------------------------------
def test_yes_after_a_restart_runs_the_confirmed_request():
    store.save_fact("my car is Audi")
    cid = context.new_conversation()
    assert engine.handle_message("forget my car", cid).data["confirmation"]
    _restart()
    r = engine.handle_message("yes", cid).data
    assert r["reply"] == "Forgotten: my car is Audi." and not store.list_facts()


def test_the_confirm_button_after_a_restart():
    store.save_fact("my car is Audi")
    cid = context.new_conversation()
    engine.handle_message("forget my car", cid)
    _restart()
    assert engine.confirm(cid, True).data["reply"] == "Forgotten: my car is Audi."


def test_no_after_a_restart_cancels_and_cannot_be_reused():
    store.save_fact("my car is Audi")
    cid = context.new_conversation()
    token = engine.handle_message("forget my car", cid).data["confirmation"]["token"]
    _restart()
    assert engine.handle_message("no", cid).data["action"] == "cancel"
    assert confirm.STORE.peek(token) is None and store.list_facts()
    assert engine.handle_message("yes", cid).data["action"] != "memory_delete" and store.list_facts()


def test_an_abandoned_confirmation_is_never_revived():
    """Asked to confirm, the user moves on to something else; a later 'yes' must not run the old request."""
    store.save_fact("my car is Audi")
    cid = context.new_conversation()
    token = engine.handle_message("forget my car", cid).data["confirmation"]["token"]
    engine.handle_message("what is 2 + 3", cid)  # a new request drops the open confirmation
    assert confirm.STORE.peek(token) is None and confirm.latest_replay(cid) is None
    _restart()
    engine.handle_message("yes", cid)
    assert store.list_facts()


def test_replays_belong_to_their_conversation():
    store.save_fact("my car is Audi")
    a, b = context.new_conversation(), context.new_conversation()
    engine.handle_message("forget my car", a)
    _restart()
    engine.handle_message("yes", b)  # another conversation's "yes"
    assert store.list_facts()
    assert engine.handle_message("yes", a).data["reply"] == "Forgotten: my car is Audi."

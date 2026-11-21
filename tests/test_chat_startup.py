"""The open chat belongs to the server process, not to the browser page. A new AppTest is a new browser session (what
F5 or reopening the tab gives); reset_process_store() is what starting `streamlit run` again gives. Offline: the
engine is replaced by a fake that saves the turn like the real one."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adhyaksh import client, db
from adhyaksh.chat import context, identity
from adhyaksh.result import Result
from adhyaksh.services import chat as svc
from tests.helpers import fresh_env

CHAT = str(Path(__file__).resolve().parent.parent / "app_pages" / "chat.py")


def _count_conversations() -> int:
    return db.query_one("SELECT COUNT(*) AS n FROM conversations")["n"]


@pytest.fixture
def env(monkeypatch):
    fresh_env()
    identity.save_name("Tester")
    monkeypatch.setattr(client, "available", lambda: False)
    monkeypatch.setattr(svc, "bridge_voice_input", lambda **kw: None)

    def fake(text, cid, voice=False, mode="cowork", attachments=None, stream=False):
        context.save_message(cid, "user", text)
        context.save_message(cid, "assistant", f"reply to {text}")
        return Result.success({"reply": "ok"})
    monkeypatch.setattr(svc, "engine_handle_message", fake)


def _session():
    """A new browser session (F5, a reopened tab)."""
    return AppTest.from_file(CHAT, default_timeout=60).run()


def test_a_new_server_run_opens_an_empty_new_chat_and_stores_nothing(env):
    old = context.new_conversation()
    context.save_message(old, "user", "an old question")
    context.save_message(old, "assistant", "an old answer")
    svc.reset_process_store()  # the server starts again
    before = _count_conversations()
    at = _session()
    assert not at.exception and at.pills, "the greeting and examples of a new chat"
    assert not any("an old answer" in m.value for m in at.markdown)
    assert svc.current_chat() is None and _count_conversations() == before, "no row until the first message"
    assert "an old question" in [b.label for b in at.sidebar.button], "old chats stay in the sidebar"


def test_the_first_message_creates_the_chat(env):
    at = _session()
    before = _count_conversations()
    at.chat_input(key="composer").set_value("what is 12 * 7").run()
    assert _count_conversations() == before + 1 and svc.current_chat() is not None
    assert [m["content"] for m in context.history(svc.current_chat(), 10)] == ["what is 12 * 7", "reply to what is 12 * 7"]


def test_f5_keeps_the_same_chat(env):
    _session().chat_input(key="composer").set_value("hello there").run()
    cid = svc.current_chat()
    again = _session()  # F5: a new browser session in the same server run
    assert svc.current_chat() == cid and any("reply to hello there" in m.value for m in again.markdown)
    assert not again.pills


def test_a_new_server_process_starts_fresh_after_f5(env):
    _session().chat_input(key="composer").set_value("hello there").run()
    svc.reset_process_store()  # the server is restarted
    at = _session()
    assert svc.current_chat() is None and at.pills and not any("reply to hello there" in m.value for m in at.markdown)


def test_new_chat_stores_nothing_until_used(env):
    _session().chat_input(key="composer").set_value("hello there").run()
    at = _session()
    before = _count_conversations()
    next(b for b in at.sidebar.button if b.label == "New chat").click().run()
    next(b for b in at.sidebar.button if b.label == "New chat").click().run()
    assert svc.current_chat() is None and _count_conversations() == before and at.pills


def test_a_deleted_current_chat_becomes_a_new_chat(env):
    cid = svc.ensure_chat()
    svc.conversation_delete(cid)
    assert svc.current_chat() is None

"""Phase 4d: the conversations sidebar on the Chat page and its service functions. Offline."""
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from adhyaksh import client, db
from adhyaksh.chat import context, identity
from adhyaksh.services import chat as svc
from tests.helpers import current_chat, fresh_env, open_chat

PAGE = str(Path(__file__).resolve().parent.parent / "app_pages" / "chat.py")


def _convo(*texts, title=None):
    cid = context.new_conversation(title or "Chat")
    for i, t in enumerate(texts):
        context.save_message(cid, "user" if i % 2 == 0 else "assistant", t)
    return cid


@pytest.fixture
def env(monkeypatch):
    fresh_env()
    identity.save_name("Tester")
    monkeypatch.setattr(client, "available", lambda: False)
    monkeypatch.setattr(svc, "bridge_voice_input", lambda **kw: None)


# ---- service ---------------------------------------------------------------------------------------------------------
def test_list_is_newest_first_titled_by_the_first_message(env):
    a = _convo("plan my trip to Goa", "Sure.")
    b = _convo("what is 12 * 7", "84")
    rows = svc.conversations_list()
    assert [r["id"] for r in rows] == [b, a]
    assert rows[0]["title"] == "what is 12 * 7" and rows[0]["count"] == 2
    context.save_message(a, "user", "and hotels?")  # new activity moves a conversation to the top
    assert svc.conversations_list()[0]["id"] == a


def test_long_first_messages_are_shortened(env):
    _convo("x" * 200)
    t = svc.conversations_list()[0]["title"]
    assert len(t) <= svc.TITLE_CHARS + 2 and t.endswith("...")


def test_empty_conversations_are_hidden_except_the_open_one(env):
    _convo("hello")
    empty = context.new_conversation()
    assert empty not in [r["id"] for r in svc.conversations_list()]
    assert svc.conversations_list(keep=empty)[0]["title"] == "New chat"


def test_search_matches_titles_and_messages_ignoring_case(env):
    a = _convo("plan my trip to Goa", "Book a train.")
    b = _convo("hello", title="Work notes")
    assert [r["id"] for r in svc.conversations_list("TRAIN")] == [a]
    assert [r["id"] for r in svc.conversations_list("work")] == [b]
    assert svc.conversations_list("nothing like this") == []
    assert svc.conversations_list("100%") == []  # % and _ are literal, not wildcards


def test_rename_and_refuse_an_empty_name(env):
    a = _convo("hello")
    assert svc.conversation_rename(a, "  My   chat ")
    assert svc.conversations_list()[0]["title"] == "My chat" == svc.conversation_title(a)
    assert not svc.conversation_rename(a, "   ")
    assert svc.conversation_title(a) == "My chat"


def test_delete_removes_messages_and_saved_replays(env):
    a = _convo("delete notes.txt", "Confirm or cancel.")
    db.execute("INSERT INTO confirm_replays(token, conversation_id, intent, text, slots_json, mode, lang, created_at)"
               " VALUES(?,?,?,?,?,?,?,?)", ("t1", a, "file_delete", "delete notes.txt", "{}", "cowork", "en", 0.0))
    svc.conversation_delete(a)
    assert not svc.conversation_exists(a)
    assert db.query_one("SELECT 1 FROM messages WHERE conversation_id=?", (a,)) is None
    assert db.query_one("SELECT 1 FROM confirm_replays WHERE conversation_id=?", (a,)) is None


def test_new_chat_reuses_an_empty_open_conversation(env):
    empty = context.new_conversation()
    assert svc.conversation_new(empty) == empty
    used = _convo("hello")
    assert svc.conversation_new(used) not in (used, empty)


# ---- page ------------------------------------------------------------------------------------------------------------
def _page(cid):
    at = AppTest.from_file(PAGE, default_timeout=60)
    open_chat(cid)
    return at.run()


def _sidebar_labels(at):
    return [b.label for b in at.sidebar.button]


def test_sidebar_lists_conversations_and_opens_one(env):
    a = _convo("plan my trip to Goa", "Sure, when?")
    b = _convo("what is 12 * 7", "84")
    at = _page(b)
    assert not at.exception
    assert "New chat" in _sidebar_labels(at) and "plan my trip to Goa" in _sidebar_labels(at)
    next(x for x in at.sidebar.button if x.label == "plan my trip to Goa").click().run()
    assert current_chat() == a and any("Sure, when?" in m.value for m in at.markdown)


def test_sidebar_search_filters_the_list(env):
    _convo("plan my trip to Goa", "ok")
    b = _convo("what is 12 * 7", "84")
    at = _page(b)
    at.sidebar.text_input(key="conv_search").input("goa").run()
    labels = _sidebar_labels(at)
    assert "plan my trip to Goa" in labels and "what is 12 * 7" not in labels


def test_new_chat_opens_an_empty_conversation(env):
    b = _convo("hello", "Hello.")
    at = _page(b)
    next(x for x in at.sidebar.button if x.label == "New chat").click().run()
    assert current_chat() is None and at.pills, "the new chat shows the greeting and examples"


def test_rename_from_the_row_menu(env):
    b = _convo("hello", "Hello.")
    at = _page(b)
    at.get_by_key("convmenu_%d" % b).set_value("Rename").run()
    form_input = next(t for t in at.sidebar.text_input if t.label == "New name")
    form_input.input("Greetings")
    next(x for x in at.sidebar.button if x.label == "Save").click().run()  # typed and submitted together
    assert svc.conversation_title(b) == "Greetings" and "Greetings" in _sidebar_labels(at)


def test_delete_asks_first_and_moves_to_another_conversation(env):
    a = _convo("first chat", "ok")
    b = _convo("second chat", "ok")
    at = _page(b)
    at.get_by_key("convmenu_%d" % b).set_value("Delete").run()
    assert svc.conversation_exists(b), "nothing is deleted before the second click"
    next(x for x in at.sidebar.button if x.label == "Cancel").click().run()
    assert svc.conversation_exists(b)
    at.get_by_key("convmenu_%d" % b).set_value("Delete").run()
    next(x for x in at.sidebar.button if x.label == "Delete").click().run()
    assert not svc.conversation_exists(b) and current_chat() == a

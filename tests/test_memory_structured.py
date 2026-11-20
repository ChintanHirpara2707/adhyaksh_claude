"""Phase 2c: structured memory. Facts are (subject, attribute, value); the same attribute updates instead of
duplicating; recall finds the asked attribute in five language styles; forgetting needs confirmation; automatic
memory is off by default and never overwrites what the user saved."""
import pytest

from adhyaksh import config, db
from adhyaksh.chat import context, engine
from adhyaksh.memory import facts, store
from adhyaksh.result import E_NEEDS_CONFIRM
from tests.helpers import fresh_env


@pytest.fixture(autouse=True)
def _env():
    fresh_env()


# ---- parsing ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,attr,value", [
    ("my locker code is 4417", "locker code", "4417"),
    ("my favourite colour is blue", "favorite color", "blue"),
    ("My Favorite Color is Red.", "favorite color", "Red"),
    ("mera birthday 12 march ko hai", "birthday", "12 march ko"),
    ("meri car Audi hai", "car", "Audi"),
    ("मेरी कार ऑडी है", "car", "ऑडी"),
    ("मेरा जन्मदिन 5 मई को है", "birthday", "5 मई को"),
    ("મારો રૂમ નંબર 204 છે", "room number", "204"),
    ("maro phone number 98765 che", "phone number", "98765"),
    ("mere dog ka naam Bruno hai", "dog name", "Bruno"),
    ("my sister's birthday is 5 may", "sister birthday", "5 may"),
])
def test_statements_become_structured_facts(text, attr, value):
    f = facts.parse_statement(text)
    assert f is not None and (f.subject, f.attribute, f.value) == ("user", attr, value)


@pytest.mark.parametrize("text", ["i like tea", "my name is not important", "the sky is blue", "remind me at 5"])
def test_other_sentences_stay_free_text(text):
    assert facts.parse_statement(text) is None


@pytest.mark.parametrize("text,attr", [
    ("what is my locker code", "locker code"), ("when is my birthday?", "birthday"), ("what's my fav color", "favorite color"),
    ("do you know my favourite colour", "favorite color"), ("mera birthday kab hai", "birthday"),
    ("मेरी कार क्या है", "car"), ("मेरा जन्मदिन कब है", "birthday"), ("મારો રૂમ નંબર શું છે", "room number"),
    ("maro birthday kyare che", "birthday"),
])
def test_questions_name_the_attribute(text, attr):
    assert facts.question_attribute(text) == attr


@pytest.mark.parametrize("text,attr", [
    ("forget my locker code", "locker code"), ("delete my car from memory", "car"), ("forget about my birthday", "birthday"),
    ("clear my locker code from your memory", "locker code"),
    ("meri car bhool jao", "car"), ("मेरी कार भूल जाओ", "car"), ("મારી કાર ભૂલી જાઓ", "car"),
    ("maro phone number bhuli jao", "phone number"),
])
def test_forget_requests_name_the_attribute(text, attr):
    assert facts.forget_attribute(text) == attr


@pytest.mark.parametrize("text", ["don't forget my car is red", "delete notes.txt", "remove chrome", "close notepad",
                                  "delete all my reminders", "remove my notes", "erase my files"])
def test_not_forget_requests(text):
    assert facts.forget_attribute(text) is None


# ---- store ------------------------------------------------------------------------------------------------
def test_same_attribute_updates_instead_of_duplicating():
    first = store.save_fact("remember that my favourite colour is blue").data
    second = store.save_fact("my favorite color is red").data
    assert second["updated"] and second["id"] == first["id"] and second["previous"] == "my favourite colour is blue"
    rows = store.list_facts()
    assert len(rows) == 1 and rows[0]["value"] == "red" and rows[0]["attribute"] == "favorite color"
    assert store.recall("what is my favourite colour").data["answer"] == "Your favorite color is red"
    assert store.save_fact("my favorite color is red").data["duplicate"]


def test_recall_by_attribute_across_languages():
    store.save_fact("मेरी कार ऑडी है")
    store.save_fact("my locker code is 4417")
    assert store.recall("meri car kya hai").data["fact"] == "मेरी कार ऑडी है"
    assert store.recall("what is my locker code").data == {**store.recall("what is my locker code").data, "match": "attribute",
                                                           "value": "4417"}
    assert store.best_match("मेरी कार क्या है")["fact"] == "मेरी कार ऑडी है"


def test_free_text_facts_still_work():
    store.save_fact("remember that the spare key is under the mat")
    row = store.list_facts()[0]
    assert row["attribute"] is None and row["subject"] == facts.GENERAL
    assert "mat" in store.recall("where is the spare key").data["fact"]


def test_old_rows_are_converted_on_first_use():
    now = db.utcnow()
    db.execute("INSERT INTO memory_facts(fact,category,created_at,updated_at) VALUES(?,?,?,?)",
               ("my exam is on Friday", "personal", now, now))
    row = store.list_facts()[0]
    assert row["attribute"] == "exam" and row["value"] == "on Friday" and row["parsed"] == 1
    assert store.recall("when is my exam").data["match"] == "attribute"


def test_forget_needs_confirmation_and_then_deletes():
    store.save_fact("my locker code is 4417")
    pending = store.forget("forget my locker code")
    assert pending.error_code == E_NEEDS_CONFIRM and store.list_facts()
    done = store.forget("forget my locker code", ctx={"token": pending.data["token"]})
    assert done.ok and done.data["fact"] == "my locker code is 4417" and not store.list_facts()
    missing = store.forget("forget my car")
    assert not missing.ok and "nothing saved about car" in missing.message


# ---- automatic memory -----------------------------------------------------------------------------------------
def test_automatic_memory_is_off_by_default_and_never_overwrites_the_user():
    assert not config.get_bool("auto_memory") and store.notice("my exam is on Friday") is None
    config.set_value("auto_memory", True)
    store.save_fact("my exam is on Monday")
    res = store.notice("my exam is on Friday")
    assert res.data["duplicate"] and store.list_facts()[0]["value"] == "on Monday"
    store.notice("my bike is a Honda")
    auto = next(r for r in store.list_facts() if r["attribute"] == "bike")
    assert auto["source"] == "auto" and auto["confidence"] < 1.0
    assert store.notice("is my bike a Honda?") is None


# ---- through the chat engine --------------------------------------------------------------------------------
def _say(cid, text):
    return engine.handle_message(text, cid).data


def test_chat_save_update_recall_forget_round_trip():
    cid = context.new_conversation()
    assert _say(cid, "remember that my car is Audi")["reply"].startswith("Saved to memory")
    r = _say(cid, "remember my car is BMW")
    assert r["reply"].startswith("Updated in memory: my car is BMW (was: my car is Audi)")
    assert "BMW" in _say(cid, "what is my car")["reply"]
    r = _say(cid, "forget my car")
    assert r["intent"] == "memory_forget" and r["confirmation"] and "Forget this: my car is BMW?" in r["reply"]
    assert engine.confirm(cid, True).data["reply"] == "Forgotten: my car is BMW."
    assert not store.list_facts()


def test_chat_forget_can_be_cancelled():
    cid = context.new_conversation()
    store.save_fact("मेरी कार ऑडी है")
    assert _say(cid, "मेरी कार भूल जाओ")["confirmation"]
    engine.confirm(cid, False)
    assert len(store.list_facts()) == 1


def test_auto_memory_through_chat():
    config.set_value("auto_memory", True)
    cid = context.new_conversation()
    _say(cid, "hello there, my exam is on Friday")
    _say(cid, "my exam is on Friday")
    rows = store.list_facts()
    assert len(rows) == 1 and rows[0]["source"] in ("auto", "user")


def test_memory_page_renders():
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    store.save_fact("my locker code is 4417")
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app_pages" / "memory.py"), default_timeout=60).run()
    assert not at.exception and any("locker code: 4417" in e.label for e in at.expander)

"""P1 fixes on the offline path: names, work folder, recall and attachment routing, unsupported requests."""
import json
import os

import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine, identity, router
from adhyaksh.memory import store
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"


@pytest.mark.parametrize("text", ["mane ek saras gazal kaho", "मुझे एक छोटी कविता कहो", "મને એક વાર્તા કહો", "call me later", "mujhe koi kahani bolo"])
def test_requests_are_not_read_as_a_name(text):
    assert identity.extract_name(text)[0] is None, text
    r = router.understand(text)
    assert r is None or r.intent != "set_identity", (text, r)


@pytest.mark.parametrize("text,name", [("mane Hardik kaho", "Hardik"), ("मुझे सुरेश कहो", "सुरेश"), ("my name is Rohan", "Rohan")])
def test_real_names_still_work(text, name):
    assert identity.extract_name(text)[0] == name


@pytest.mark.parametrize("text,intent,key,value", [
    ("delete the file old budget.txt", "file_delete", "file", "old budget.txt"),
    ("write pay rent at the end of tasks.txt", "file_update", "content", "pay rent"),
    ("add \"ring the plumber\" to tasks.txt", "file_update", "file", "tasks.txt"),
    ("tasks.txt में चाय और चीनी जोड़ दो", "file_update", "content", "चाय और चीनी"),
    ("hisab.txt me likh do \"diesel 900\"", "file_update", "content", "diesel 900"),
    ("Reports नाम का फोल्डर बनाओ", "folder_create", "folder", "Reports"),
    ("Kharch naam nu folder banavi do", "folder_create", "folder", "Kharch"),
    ("find all my excel files", "file_search", "file", ".xlsx"),
    ("do i have a file called tax_2025.pdf", "file_search", "file", "tax_2025.pdf"),
    ("whats inside diary.txt", "file_read", "file", "diary.txt"),
])
def test_names_and_content_come_from_the_right_words(text, intent, key, value):
    r = router.understand(text)
    assert r is not None and r.intent == intent and r.slots.get(key) == value, (text, r)


@pytest.mark.parametrize("text", ["uninstall vlc", "format the d drive", "update windows now", "pay 200 rupees to the shop",
                                  "मम्मी को मैसेज भेजो", "turn on airplane mode"])
def test_unsupported_requests_are_refused(text):
    r = router.understand(text)
    assert r is not None and r.intent == "out_of_scope", (text, r)


@pytest.mark.parametrize("text,intent", [("turn off the bluetooth", "radio_control"), ("कंप्यूटर बंद कर दो", "power_action"),
                                         ("pc bandh kari do", "power_action")])
def test_radio_and_power_requests_are_supported_since_phase_2b(text, intent):
    """These were refused before Phase 2b; they now reach real tools (level 2: the user confirms first)."""
    r = router.understand(text)
    assert r is not None and r.intent == intent, (text, r)


@pytest.mark.parametrize("text,intent", [("shut the notepad", "app_close"), ("google best laptops under 50000", "web_open"),
                                         ("जीमेल खोलो", "web_open"), ("is my drive full", "system_status"),
                                         ("what should i call you", "bot_identity"), ("what do you call me", "get_identity"),
                                         ("where is my passport", "memory_recall"), ("do you know my pin code", "memory_recall")])
def test_more_routing(text, intent):
    r = router.understand(text)
    assert r is not None and r.intent == intent, (text, r)


def test_pending_file_name_answer_is_cleaned():
    assert router.clean_slot_name("call it shopping list") == "shopping list"
    assert router.clean_slot_name("naam hisab rakho") == "hisab"
    assert router.clean_slot_name("\"notes\"") == "notes"


def test_default_work_folder_is_used_by_every_file_tool():
    base = fresh_env()
    root = base / "root"
    root = root.resolve() if root.exists() else root
    work = root / "inner" / "work"
    work.mkdir(parents=True)
    root, work = root.resolve(), work.resolve()
    ok, _ = config.configure_folders([str(root)], str(work))
    assert ok
    cid = context.new_conversation()
    say = lambda t: engine.handle_message(t, cid).data["reply"]  # noqa: E731
    assert str(work / "a1.txt") in say("create a file named a1.txt")
    assert str(work / "Proj") in say("make a folder named Proj")
    assert str(work) in say("create an excel sheet named ex1.xlsx")
    assert (work / "a1.txt").exists() and (work / "Proj").is_dir() and not (root / "a1.txt").exists()
    assert "Which file name" in say("create a file") and str(work / "my list.txt") in say("call it my list")


def test_memory_and_attachment_questions_are_answered_from_context_not_guessed():
    fresh_env()
    cid = context.new_conversation()
    say = lambda t, **k: engine.handle_message(t, cid, **k).data  # noqa: E731
    say("remember that my cat is named Simba")
    r = say("what is the name of the cat")  # no "my", no trained model: still answered from memory
    assert r["intent"] == "memory_recall" and "Simba" in r["reply"]
    assert store.best_match("what is the capital of France") is None
    r = say("what is the warranty period", attachments=[("w.txt", b"The warranty period for the mixer is two years from purchase.")])
    assert r["intent"] == "doc_question" and "two years" in r["reply"]
    r = say("how long is the warranty for the mixer")  # follow-up without re-attaching
    assert r["intent"] == "doc_question" and "two years" in r["reply"]
    r = say("what colour is the roof", attachments=[("w2.txt", b"Completely unrelated text about cooking rice.")])
    assert r["intent"] == "doc_question" and "could not find that in the attached file" in r["reply"]

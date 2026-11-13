"""Command understanding: filler stripping, synonyms, typos and code-mixed phrasing (rules only, no model)."""
import pytest

from adhyaksh.chat import router
from tests.helpers import fresh_env


@pytest.fixture(autouse=True)
def _env():
    fresh_env()


@pytest.mark.parametrize("text,expected", [
    ("hey assistant, can you open notepad please", "open notepad"),
    ("could you please take a screenshot now", "take a screenshot"),
    ("zara calculator kholo yaar", "calculator kholo"),
    ("open notepad", "open notepad"),
])
def test_clean_command(text, expected):
    assert router.clean_command(text) == expected


@pytest.mark.parametrize("text,intent,slot", [
    ("launch notepad", "app_open", ("app", "notepad")),
    ("please fire up the calculator", "app_open", ("app", "calculator")),
    ("start notpad", "app_open", ("app", "notepad")),
    ("calculator chalu karo", "app_open", ("app", "calculator")),
    ("quit notepad", "app_close", ("app", "notepad")),
    ("kill calculator", "app_close", ("app", "calculator")),
    ("notepad band karo", "app_close", ("app", "notepad")),
    ("notepad બંધ કરો", "app_close", ("app", "notepad")),
    ("grab a screenshot", "screenshot", None),
    ("screenshot lo", "screenshot", None),
    ("how is my cpu usage", "system_status", None),
    ("check ram and disk space", "system_status", None),
    ("is my laptop slow, show health", "system_status", None),
    ("kitne baje hain", "time_date", ("kind", "time")),
    ("what time is it", "time_date", ("kind", "time")),
    ("aaj ki tarikh kya hai", "time_date", ("kind", "date")),
    ("show notes.txt", "file_read", ("file", "notes.txt")),
    ("please delete old.txt", "file_delete", ("file", "old.txt")),
    ("locate budget.xlsx", "file_search", ("file", "budget.xlsx")),
    ("make a file todo.txt", "file_create", ("file", "todo.txt")),
    ("remember that my bike is a Honda", "memory_save", None),
    ("do you remember my bike", "memory_recall", None),
])
def test_understand(text, intent, slot):
    rule = router.understand(text)
    assert rule is not None and rule.intent == intent, (text, rule)
    if slot:
        assert rule.slots.get(slot[0]) == slot[1], (text, rule)


@pytest.mark.parametrize("text", [
    "tell me about black holes", "who is the CEO of Google", "I remember nothing today",
    "open the pod bay doors", "explain how the cpu works in a computer",
])
def test_no_false_positives(text):
    rule = router.understand(text)
    assert rule is None or rule.intent not in {"app_open", "app_close", "screenshot", "file_delete"}, (text, rule)

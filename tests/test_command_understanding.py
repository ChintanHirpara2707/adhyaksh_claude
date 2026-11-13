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


@pytest.mark.parametrize("text,intent", [
    ("what's my name", "get_identity"), ("whats my name", "get_identity"), ("tell me my name", "get_identity"),
    ("batao na mera naam kya hai", "get_identity"), ("maru naam kaho ne", "get_identity"),
    ("क्या आपको मेरा नाम याद है", "get_identity"), ("મારું નામ યાદ છે તમને", "get_identity"),
    ("मुझे सुरेश बुलाओ", "set_identity"), ("aap mujhe Neha naam se pukaro", "set_identity"),
    ("my name is Rohan", "set_identity"),
    ("ok bye", "smalltalk"), ("thx bro", "smalltalk"), ("okay thank you so much", "smalltalk"), ("good night", "smalltalk"),
    ("bhai tumhare features kya hain", "help"), ("what are you capable of", "help"),
])
def test_conversational_rules(text, intent):
    rule = router.understand(text)
    assert rule is not None and rule.intent == intent, (text, rule)


@pytest.mark.parametrize("text,intent", [
    ("આજે કયો દિવસ છે", "time_date"), ("which weekday is it", "time_date"), ("what's the time", "time_date"),
    ("સીપીયુ વપરાશ કેટલો છે", "system_status"), ("मेरा लैपटॉप धीमा क्यों है", "system_status"),
    ("ye note kar lo ki mera laptop Dell hai", "memory_save"), ("bhulta nahi maru bill 500 nu che", "memory_save"),
    ("what is my locker code", "memory_recall"), ("mari bike kaun si che kaho", "memory_recall"),
    ("add a line to plan.txt saying buy milk", "file_update"), ("append \"done\" to todo.txt", "file_update"),
    ("plan.txt में नया टेक्स्ट जोड़ो", "file_update"), ("एक्सेल शीट sales2.xlsx बनाओ", "office_create"),
    ("ss le lo", "screenshot"), ("capture whatever is on my display", "screenshot"),
    ("arre bhai namaste", "greet"), ("કેમ છો મિત્ર", "greet"),
    ("create a file", "file_create"), ("make a new folder", "folder_create"),
])
def test_more_generic_rules(text, intent):
    rule = router.understand(text)
    assert rule is not None and rule.intent == intent, (text, rule)


@pytest.mark.parametrize("text", [
    "write a short story about volcanoes", "why is the sky blue", "who invented the telephone", "how do magnets work",
    "my name is Rohan", "remember that my bike is a Honda",
])
def test_knowledge_not_hijacked_by_rules(text):
    rule = router.understand(text)
    assert rule is None or rule.intent in {"set_identity", "memory_save"}, (text, rule)


@pytest.mark.parametrize("text,intent", [
    ("clse notepad", "app_close"), ("opn calculator", "app_open"),
    ("pls open youtube site", "web_open"), ("youtube khol de bhai", "web_open"), ("gmail kholi do", "web_open"),
    ("whats 50% of 200", "math"), ("what is 17 mod 5", "math"),
    ("dont forget my wifi password is blue42", "memory_save"),
    ("meri meeting kitne baje hai yaad hai", "memory_recall"),
    ("tamari pase kya kya suvidha che", "help"), ("what's my name", "get_identity"),
])
def test_typos_and_phrasing(text, intent):
    rule = router.understand(text)
    assert rule is not None and rule.intent == intent, (text, rule)


def test_read_is_not_append_and_math_values():
    assert router.understand("plan.txt में क्या लिखा है दिखाओ") is None or router.understand("plan.txt में क्या लिखा है दिखाओ").intent != "file_update"
    assert router.understand("whats 50% of 200").slots["value"] == 100
    assert router.understand("what is 17 mod 5").slots["value"] == 2
    assert router.find_folder_name("ek folder banao jiska naam Notes3 ho") == "Notes3"

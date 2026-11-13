"""Free-form memory commands: the verb can come before or after the data, in five languages (rules only, no model).

None of these phrasings is in the training data; test_phrasings_not_in_training enforces that."""
import pytest

from adhyaksh.chat import context, engine, router
from adhyaksh.memory import store
from tests.helpers import fresh_env

# (utterance, expected stored fact)
SAVE_CASES = [
    ("my wifi router is in the hall cupboard, save this in your memory", "my wifi router is in the hall cupboard"),
    ("Please save this in memory: the dentist is on 12th at 4 pm", "the dentist is on 12th at 4 pm"),
    ("store in your memory that my cousin lives in Pune", "my cousin lives in Pune"),
    ("The gate code is 7788. Remember this.", "The gate code is 7788"),
    ("remember my passport expires in March 2029", "my passport expires in March 2029"),
    ("don't forget the electricity bill is due on the 5th", "the electricity bill is due on the 5th"),
    ("my sister's birthday is 9 June, please note this down", "my sister's birthday is 9 June"),
    ("मेरी चाबी अलमारी में है, यह याद रखना", "मेरी चाबी अलमारी में है"),
    ("याद रखो कि कल दवाई लेनी है", "कल दवाई लेनी है"),
    ("मेरा लैपटॉप चार्जर बैग में है इसे सेव कर लो", "मेरा लैपटॉप चार्जर बैग में है"),
    ("મારી બેગ કબાટમાં છે આ યાદ રાખજો", "મારી બેગ કબાટમાં છે"),
    ("સેવ કરો કે કાલે મીટિંગ સાંજે પાંચ વાગ્યે છે", "કાલે મીટિંગ સાંજે પાંચ વાગ્યે છે"),
    ("kal ki meeting 11 baje hai ye yaad rakhna", "kal ki meeting 11 baje hai"),
    ("mera dentist appointment shanivar ko hai, isko save kar do", "mera dentist appointment shanivar ko hai"),
    ("save kar lo ki mera bank locker 14 number ka hai", "mera bank locker 14 number ka hai"),
    ("maru passport drawer ma che aa yaad rakhjo", "maru passport drawer ma che"),
    ("aane save kari lo: mari gaadi nu insurance June ma pure thay che", "mari gaadi nu insurance June ma pure thay che"),
    ("note kari lo ke kal doctor ne malvanu che", "kal doctor ne malvanu che"),
]
ASK_CASES = ["save this in memory", "remember this", "please store it in your memory", "ye yaad rakhna", "આ યાદ રાખજો", "याद रखो"]
MULTILINE = "Shopping list:\n- rice\n- dal\n- 2 litres milk\n\nMeeting notes: budget approved on Friday.\nsave this in your memory"


@pytest.mark.parametrize("text,fact", SAVE_CASES)
def test_save_detects_verb_anywhere_and_strips_it(text, fact):
    rule = router.understand(text)
    assert rule is not None and rule.intent == "memory_save", (text, rule)
    assert rule.slots.get("fact", "").rstrip(".!। ") == fact, (text, rule.slots)


@pytest.mark.parametrize("text", ASK_CASES)
def test_command_only_asks_what_to_remember(text):
    rule = router.understand(text)
    assert rule is not None and rule.intent == "memory_save" and rule.slots.get("ask"), (text, rule)


def test_multiline_text_is_kept_whole():
    rule = router.understand(MULTILINE)
    assert rule.intent == "memory_save"
    assert rule.slots["fact"].startswith("Shopping list:\n- rice") and "budget approved on Friday." in rule.slots["fact"]
    assert "save this" not in rule.slots["fact"]


@pytest.mark.parametrize("text", [
    "save notes.txt", "save the report.docx in the workspace", "delete my old memory.txt", "how do I remember names better",
    "do you remember my bike", "what is a memory leak", "open notepad", "take a screenshot",
])
def test_not_a_memory_save(text):
    rule = router.understand(text)
    assert rule is None or rule.intent != "memory_save", (text, rule)


def test_engine_saves_asks_once_and_recalls():
    fresh_env()
    cid = context.new_conversation()
    say = lambda t: engine.handle_message(t, cid).data  # noqa: E731
    r = say("my wifi router is in the hall cupboard, save this in your memory")
    assert r["intent"] == "memory_save" and "hall cupboard" in r["reply"] and "save this" not in r["reply"]
    r = say("save this in memory")
    assert r["reply"] == "What should I remember?"
    r = say("my gym locker number is 88")
    assert "gym locker number is 88" in r["reply"]
    assert [f["fact"] for f in store.list_facts()][:2] == ["my gym locker number is 88", "my wifi router is in the hall cupboard"]
    r = say(MULTILINE)
    assert "Shopping list" in store.list_facts()[0]["fact"] and "\n" in store.list_facts()[0]["fact"]
    # recall
    assert "hall cupboard" in say("where is my wifi router")["reply"] or "hall cupboard" in say("what is my wifi router")["reply"]
    assert "gym locker" in say("what is my gym locker number")["reply"]
    listing = say("what do you remember")["reply"]
    assert listing.startswith("I remember 3 item(s)") and "hall cupboard" in listing and "gym locker" in listing
    assert say("tum kya kya yaad rakhte ho")["intent"] in {"memory_recall", "unknown", "knowledge_question"}


def test_long_text_over_old_limit_is_saved():
    fresh_env()
    cid = context.new_conversation()
    body = "note " + " ".join(f"word{i}" for i in range(600))  # > 2000 characters
    r = engine.handle_message("remember: " + body, cid).data
    assert r["intent"] == "memory_save" and len(store.list_facts()[0]["fact"]) > 2000


def test_phrasings_not_in_training():
    import csv
    from adhyaksh.nlu import dataset
    train = {t.lower().strip() for t in dataset.load()["text"]}
    texts = [t for t, _ in SAVE_CASES] + ASK_CASES + [MULTILINE]
    assert not [t for t in texts if t.lower().strip() in train]

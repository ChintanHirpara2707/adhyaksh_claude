"""Phase 1b: frame-based NLU. Action and polarity decided apart from the target, negation in five language
styles, clean entities, leftovers handed to the richer rules, and the local fast path when a model is configured."""
import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine
from adhyaksh.llm import base as llm
from adhyaksh.nlu import entities, frames, lexicon
from adhyaksh.result import Result
from tests.helpers import fresh_env


@pytest.fixture(autouse=True)
def _env():
    fresh_env()


# ---- polarity: every opposite verb on every target --------------------------------------------------------
@pytest.mark.parametrize("lang", lexicon.LANGS)
def test_every_open_and_close_verb_keeps_its_polarity(lang):
    target = {"hi": "क्रोम", "gu": "ક્રોમ"}.get(lang, "chrome")
    for action, intent in (("open", "app_open"), ("close", "app_close")):
        for verb in lexicon.ACTIONS[action][lang]:
            text = f"{verb} {target}" if lexicon.VERB_FIRST[lang] else f"{target} {verb}"
            frame = frames.command(text)
            assert frame is not None and frame.intent == intent and frame.target == "chrome", (text, frames.parse(text))


@pytest.mark.parametrize("lang", lexicon.LANGS)
def test_every_create_and_delete_verb_keeps_its_polarity(lang):
    for action, intent in (("create", "file_create"), ("delete", "file_delete")):
        for verb in lexicon.ACTIONS[action][lang]:
            if verb in ("start a new", "set up", "where is"):
                continue
            text = f"{verb} plan.txt" if lexicon.VERB_FIRST[lang] else f"plan.txt {verb}"
            frame = frames.command(text)
            assert frame is not None and frame.intent == intent and frame.target == "plan.txt", (text, frames.parse(text))


# ---- negation ---------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "don't open notepad", "do not close chrome", "never delete report.txt", "no need to open calculator",
    "I don't want you to close spotify", "wait, don't open paint", "can you not open chrome",
    "notepad mat kholo", "chrome band mat karo", "report.txt delete nahi karna", "abhi calculator mat chalu karna",
    "notepad na kholo", "chrome bandh na karo", "list.txt kadhi na nakho",
    "नोटपैड मत खोलो", "क्रोम बंद मत करो", "report.txt मत हटाओ", "नोटपैड नहीं खोलना",
    "નોટપેડ ના ખોલો", "ક્રોમ બંધ ના કરો", "report.txt કાઢી ના નાખો", "નોટપેડ ખોલવું નહીં",
])
def test_negated_commands_are_detected(text):
    frame = frames.negated_command(text)
    assert frame is not None and frame.negated, text
    assert frames.command(text) is None


@pytest.mark.parametrize("text", [
    "calculator chalu karo na", "chrome band karo na please", "बंद करो ना क्रोम", "notepad kholo ne",
    "dont forget my wifi password is blue42", "remember that i should not open chrome after 10 pm",
    "remind me not to delete report.txt", "why is chrome not opening?", "is notepad not running",
    "write do not open in notes.txt",
])
def test_emphasis_idioms_questions_and_other_commands_are_not_negations(text):
    assert frames.negated_command(text) is None, (text, frames.parse(text))


def test_negated_request_runs_nothing_and_says_so(monkeypatch):
    ran = []
    monkeypatch.setattr(engine.apps, "open_app", lambda *a, **k: ran.append(a) or Result.success({}))
    monkeypatch.setattr(engine.files, "delete", lambda *a, **k: ran.append(a) or Result.success({}))
    r = engine.handle_message("don't open notepad", context.new_conversation()).data
    assert r["intent"] == "negated" and r["reply"].startswith("Okay, I won't open notepad") and not ran
    r = engine.handle_message("report.txt मत हटाओ", context.new_conversation()).data
    assert r["intent"] == "negated" and "report.txt" in r["reply"] and not ran


# ---- entities -------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,app", [
    ("open note pad", "notepad"), ("close crome", "chrome"), ("launch google chrome", "chrome"),
    ("open visual studio code", "vs code"), ("स्पॉटिफाई खोलो", "spotify"), ("વોટ્સએપ ખોલો", "whatsapp"),
    ("open code", "vs code"), ("edge kholi do", "edge"), ("mujhe paint chahiye", "paint"),
])
def test_app_entity_is_canonical(text, app):
    assert entities.find_app(text, fuzzy=True) == app


@pytest.mark.parametrize("text", ["remember that my locker code is 4417", "run python code", "what does this code do",
                                  "on the edge of the table"])
def test_everyday_words_are_not_apps(text):
    assert entities.find_app(text) is None


@pytest.mark.parametrize("url,clean", [("github.com", "https://github.com"), ("HTTP://Example.COM/Path", "http://example.com/Path"),
                                       ("https://youtube.com/watch?v=1", "https://youtube.com/watch?v=1"), ("site.in.", "https://site.in")])
def test_urls_are_normalised(url, clean):
    assert entities.normalize_url(url) == clean


def test_file_and_process_entities():
    assert entities.find_file("create a file called meeting notes.txt") == "meeting notes.txt"
    assert entities.find_file("go to github.com") is None  # a website, not a file
    assert entities.named("search for files named invoice") == "invoice"
    assert entities.clean_process_target("for notepad.exe") == "notepad.exe"


# ---- leftovers go to the richer rules -----------------------------------------------------------------------
@pytest.mark.parametrize("text", ["create notes.txt with hello world", "create notes.txt in Projects folder",
                                  "open notepad and close chrome", "close chrome then open paint"])
def test_requests_with_more_than_action_and_target_are_not_claimed(text):
    assert frames.command(text) is None


def test_default_work_folder_location_is_absorbed():
    frame = frames.command("create groceries.txt in my work folder")
    assert frame.intent == "file_create" and frame.slots() == {"file": "groceries.txt"}


# ---- local fast path when a model is configured ---------------------------------------------------------------
def test_simple_command_runs_locally_without_the_model(monkeypatch):
    config.set_value("llm_provider", "ollama")
    asked = []
    monkeypatch.setattr(llm, "chat", lambda *a, **k: asked.append(a) or Result.success({"text": "hi", "tool_calls": []}))
    opened = []
    monkeypatch.setattr(engine.apps, "open_app", lambda app, **k: opened.append(app) or Result.success({"app": app}))
    r = engine.handle_message("spotify chalu karo", context.new_conversation()).data
    assert opened == ["spotify"] and not asked and r["reply"] == "Opened spotify."
    engine.handle_message("open notepad and tell me a joke", context.new_conversation())
    assert asked  # anything more than one plain command still goes to the model


def test_llm_first_routing_sends_everything_to_the_model(monkeypatch):
    config.set_value("llm_provider", "ollama")
    config.set_value("routing", "llm_first")
    asked = []
    monkeypatch.setattr(llm, "chat", lambda *a, **k: asked.append(a) or Result.success({"text": "Okay.", "tool_calls": []}))
    engine.handle_message("open notepad", context.new_conversation())
    assert asked


def test_negation_is_enforced_even_when_a_model_is_configured(monkeypatch):
    config.set_value("llm_provider", "ollama")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: Result.success(
        {"text": "", "tool_calls": [{"id": "x", "name": "app_open", "arguments": {"app": "notepad"}}]}))
    opened = []
    monkeypatch.setattr(engine.apps, "open_app", lambda app, **k: opened.append(app) or Result.success({"app": app}))
    r = engine.handle_message("notepad mat kholo", context.new_conversation()).data
    assert r["intent"] == "negated" and not opened

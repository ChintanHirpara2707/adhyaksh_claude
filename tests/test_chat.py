import json
import os
import statistics

from adhyaksh import config, db
from adhyaksh.chat import context, engine, identity, router
from adhyaksh.memory import store
from adhyaksh.nlu import train
from adhyaksh.safety import audit
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"
_STATE = {}


def _boot():
    """One trained environment shared by the engine tests."""
    if _STATE:  # other tests may have switched the data dir; restore ours
        os.environ["ADHYAKSH_DATA_DIR"] = _STATE["data"]
        os.environ["ADHYAKSH_MODELS_DIR"] = _STATE["models"]
    else:
        base = fresh_env()
        _STATE["data"], _STATE["models"] = os.environ["ADHYAKSH_DATA_DIR"], os.environ["ADHYAKSH_MODELS_DIR"]
        ws = base / "ws"
        ws.mkdir()
        config.set_value("allowed_folders", json.dumps([str(ws)]))
        config.set_value("default_work_folder", str(ws))
        train.train_all(42, kinds=["m1_logreg", "m3_svm"], write_report=False)
        _STATE["ws"] = ws
    return _STATE["ws"]


def _say(cid, text):
    return engine.handle_message(text, cid).data


def test_identity_cases():
    cases = {"I am your new user Chintan": "Chintan", "my name is Priya Shah": "Priya Shah", "call me Raj": "Raj",
             "mera naam Amit hai": "Amit", "maru naam Hiral che": "Hiral"}
    for text, want in cases.items():
        assert identity.extract_name(text)[0] == want, text
    for text in ("I am ready", "I am fine", "I am your assistant"):
        assert identity.extract_name(text) == (None, 0.0), text
    assert 0 < identity.extract_name("I'm Chintan")[1] < 0.75  # low confidence: ask first


def test_safe_math():
    assert router.safe_eval("2+2*3") == 8 and router.safe_eval("-(4-6)**2") == -4
    for bad in ("__import__('os')", "1+a", "open('x')", "2**9999", "(1).real", "1;2"):
        try:
            router.safe_eval(bad)
        except ValueError:
            continue
        raise AssertionError(bad)
    assert router.match_rules("what is 15 * 3").slots["value"] == 45
    assert router.match_rules("hello there friend") is None


def test_memory_store_persists_and_dedupes():
    fresh_env()
    r = store.save_fact("remember that my car is Audi")
    assert r.ok and not r.data["duplicate"] and r.data["fact"] == "my car is Audi"
    assert store.save_fact("My car is Audi.").data["duplicate"]
    store.save_fact("my favorite color is blue")
    assert store.recall("what is my car?").data["answer"] == "Your car is Audi"
    assert store.recall("what is my favorite color").data["answer"] == "Your favorite color is blue"
    assert not store.recall("what is my passport").ok
    assert len(store.list_facts("car")) == 1
    fid = store.list_facts("car")[0]["id"]
    assert store.update_fact(fid, "my car is BMW").ok and store.recall("my car").data["fact"] == "my car is BMW"
    store.delete_fact(fid)
    assert not store.recall("my car").ok
    # persistence across 'restarts': a new connection sees the data
    assert len(store.list_facts()) == 1


def test_reference_resolution_and_confirmation():
    ws = _boot()
    cid = context.new_conversation()
    assert "File created" in _say(cid, "create notes.txt")["reply"]
    r = _say(cid, "delete it")
    assert r["confirmation"] and "notes.txt" in r["reply"] and (ws / "notes.txt").exists()
    assert _say(cid, "yes")["action"] == "file_delete" and not (ws / "notes.txt").exists()
    _say(cid, "create keep.txt")
    assert _say(cid, "delete it")["confirmation"]
    assert "cancelled" in _say(cid, "cancel")["reply"].lower() and (ws / "keep.txt").exists()


def test_missing_slot_asks_exactly_one_question():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "create a file")
    assert r["reply"] == "Which file name should I use?"
    assert "File created" in _say(cid, "slotfile.txt")["reply"] and (ws / "slotfile.txt").exists()


def test_traversal_and_identity_flows():
    ws = _boot()
    cid = context.new_conversation()
    assert "outside the allowed" in _say(cid, "read ../secret.txt")["reply"]
    assert _say(cid, "I am your new user Chintan")["reply"] == "Welcome, Chintan. Your profile has been saved."
    assert _say(cid, "what is my name")["reply"] == "Your name is Chintan."
    n = len(store.list_facts())
    assert identity.get_name() == "Chintan"
    assert "Should I address you as Chintan?" not in _say(cid, "I am ready")["reply"]
    assert "Should I address you as Raj?" in _say(cid, "I'm Raj")["reply"]
    assert "Welcome, Raj" in _say(cid, "yes")["reply"] and len(store.list_facts()) == n


def test_excel_example_through_chat():
    ws = _boot()
    cid = context.new_conversation()
    r = _say(cid, "open Excel and write 5 Indian names in 5 rows")
    assert r["reply"].startswith("Created names") and "5 rows" in r["reply"]
    from openpyxl import load_workbook
    path = next(p for p in ws.glob("names*.xlsx"))
    assert load_workbook(path).active["A5"].value


def test_every_chat_tool_action_audited_once():
    ws = _boot()
    cid = context.new_conversation()
    before = audit.count()
    _say(cid, "create audit1.txt")
    assert audit.count() == before + 1


def test_latency_p95_under_one_second():
    _boot()
    cid = context.new_conversation()
    msgs = ["hello", "remember that my room number is 204", "what is my room number", "2+2", "help",
            "create lat%d.txt", "read lat%d.txt", "list files", "मेरा नाम अमित है", "qwerty asdf"]
    times = []
    for i in range(6):
        for m in msgs:
            r = _say(cid, m % i if "%d" in m else m)
            times.append(r["latency_ms"])
    p95 = sorted(times)[int(len(times) * 0.95) - 1]
    assert p95 < 1000, p95
    print("chat p95 ms", round(p95, 1), "median", round(statistics.median(times), 1))

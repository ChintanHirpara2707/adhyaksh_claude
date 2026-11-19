"""The NLU eval case file stays well-formed: known suites and tools, complete pairs of opposite actions, every
language style covered, and no case copied from the training data."""
import csv
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CASES = ROOT / "tests" / "eval" / "nlu_cases.csv"
TOOLS = {"open_app", "close_app", "create", "read", "update", "delete", "search", "create_folder", "save_fact",
         "recall", "reminder_add", "reminder_cancel", "clipboard_read", "clipboard_write", "web_open", "process_kill",
         "screenshot", "forget_fact", "none"}


def _rows():
    with CASES.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def test_cases_are_well_formed():
    rows = _rows()
    assert len({r["id"] for r in rows}) == len(rows)
    for r in rows:
        assert r["suite"] in ("polarity", "slots", "negation"), r["id"]
        assert r["expect_tool"] in TOOLS, r["id"]
        assert r["language"] in ("en", "hi", "gu", "hinglish", "gujlish"), r["id"]
        assert (r["expect_tool"] == "none") == (r["suite"] == "negation"), r["id"]


def test_polarity_pairs_are_opposites_on_one_target():
    pairs = {}
    for r in _rows():
        if r["suite"] == "polarity":
            pairs.setdefault(r["pair"], []).append(r)
    assert len(pairs) >= 25
    for pid, members in pairs.items():
        assert len(members) == 2, pid
        a, b = members
        assert a["expect_tool"] != b["expect_tool"] and a["language"] == b["language"], pid


def test_every_language_style_in_every_suite():
    rows = _rows()
    for suite in ("polarity", "slots", "negation"):
        langs = Counter(r["language"] for r in rows if r["suite"] == suite)
        assert set(langs) == {"en", "hi", "gu", "hinglish", "gujlish"}, (suite, langs)


def test_no_case_is_in_the_training_data():
    with (ROOT / "data" / "intents.csv").open(encoding="utf-8", newline="") as f:
        train = {" ".join(r["text"].casefold().split()) for r in csv.DictReader(f)}
    leaked = [r["id"] for r in _rows() if " ".join(r["text"].casefold().split()) in train]
    assert not leaked, leaked

"""Real-world evaluation. Run: python tests/eval/run_real_eval.py [--label "P1 after fixes"]

Sends every row of data/test_real.csv (hand-written commands in five language styles, one group per product
feature) through engine.handle_message with all tools mocked, offline (no language model, no network), using a
model set trained fresh in a temporary folder. Writes tests/eval/real_results.csv and docs/REAL_EVAL.md, and
appends one line per run to tests/eval/real_history.csv so pass rates can be compared phase by phase.

The offline path is what is measured here. The language-model agent path is covered by unit tests with a
scripted fake model (tests/test_agent_native.py), because no real model is called in tests.
"""
from __future__ import annotations

import csv
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(ROOT))

from tests.eval import run_eval as base  # noqa: E402

FEATURES = ["chat", "memory", "files", "apps", "system", "processes", "reminders", "clipboard", "notebook",
            "voice", "vision", "multi-step", "safety"]
CASES = ROOT / "data" / "test_real.csv"
RESULTS = ROOT / "tests" / "eval" / "real_results.csv"
HISTORY = ROOT / "tests" / "eval" / "real_history.csv"
REPORT = ROOT / "docs" / "REAL_EVAL.md"
# Targets from docs/ROADMAP.md (percent of cases passed, offline path).
TARGETS = {"chat": 90, "memory": 90, "files": 90, "apps": 90, "system": 90, "processes": 85, "reminders": 85,
           "clipboard": 85, "notebook": 85, "voice": 90, "vision": 85, "multi-step": 70, "safety": 100}


def load_cases() -> list[dict]:
    with CASES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["section"] = r["feature"]
    return rows


def run(label: str = "") -> dict:
    rows = load_cases()
    base.build_env()
    calls: list[str] = []
    patches = base.mocked_tools(calls)
    for p in patches:
        p.start()
    try:
        results = [base.run_case(r, calls) for r in rows]
    finally:
        for p in patches:
            p.stop()
    with RESULTS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    by_feat = base.rates(results, "section")
    by_lang = base.rates(results, "language")
    total_ok = sum(r["pass"] == "PASS" for r in results)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    new_file = not HISTORY.exists()
    with HISTORY.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["time", "label", "all"] + FEATURES)
        w.writerow([stamp, label, f"{total_ok}/{len(results)}"] + [f"{by_feat.get(k, (0, 0))[0]}/{by_feat.get(k, (0, 0))[1]}" for k in FEATURES])
    write_report(results, by_feat, by_lang, total_ok, stamp, label)
    leak = base.leaked(results)
    if leak:
        print(f"WARNING: {len(leak)} test_real utterances are in the training file: {leak[:5]}")
    print(f"{label or 'run'}: {total_ok}/{len(results)} passed ({100 * total_ok / len(results):.1f}%)")
    for k in FEATURES:
        a, b = by_feat.get(k, (0, 0))
        print(f"  {k:11s} {a:3d}/{b:<3d} {100 * a / b if b else 0:5.1f}%  target {TARGETS[k]}%")
    return {"total": (total_ok, len(results)), "features": by_feat}


def write_report(results, by_feat, by_lang, total_ok, stamp, label) -> None:
    n = len(results)
    L = ["# Real-world evaluation (data/test_real.csv)", "",
         f"Latest run: {stamp}" + (f" ({label})" if label else "") + f". {n} hand-written commands, tools mocked, offline path "
         "(rules and the trained classifier; no language model).", "",
         f"**Overall: {base.pct(total_ok, n)}**", "",
         "| Feature | Pass rate | Target | Met |", "|---|---|---|---|"]
    for k in FEATURES:
        a, b = by_feat.get(k, (0, 0))
        rate = 100 * a / b if b else 0
        L.append(f"| {k} | {base.pct(a, b)} | {TARGETS[k]}% | {'yes' if rate >= TARGETS[k] else 'no'} |")
    L += ["", "| Language | Pass rate |", "|---|---|"]
    L += [f"| {g} | {base.pct(*by_lang[g])} |" for g in base.LANG_ORDER if g in by_lang]
    if HISTORY.exists():
        with HISTORY.open(encoding="utf-8", newline="") as f:
            hist = list(csv.reader(f))
        L += ["", "## History (one row per run)", "", "| " + " | ".join(hist[0]) + " |", "|" + "---|" * len(hist[0])]
        L += ["| " + " | ".join(r) + " |" for r in hist[1:]]
    fails = [r for r in results if r["pass"] == "FAIL"]
    L += ["", f"## Failures ({len(fails)})", "", "| id | Feature | Lang | Utterance | Expected | Predicted | Reason |", "|---|---|---|---|---|---|---|"]
    for r in fails:
        L.append(f"| {r['id']} | {r['section']} | {r['language']} | {r['utterance'].replace('|', '/')} | {r['expected_intent']} "
                 f"| {r['predicted_intent']} | {r['reason']}: {r['detail']} |")
    L += ["", "Notes: a case passes only when the intent matches and every outcome token holds (`tool:NAME` the mock tool "
          "ran, `arg:TEXT` some tool argument contains the text, `reply:TEXT`, `attach` a file was attached, `notool` no "
          "tool ran). This file is a held-out measure: none of its sentences may be added to the training data."]
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    lab = ""
    if "--label" in sys.argv:
        lab = sys.argv[sys.argv.index("--label") + 1]
    out = run(lab)
    if "--min-rate" in sys.argv:  # CI gate: fail below this pass rate (percent)
        need = float(sys.argv[sys.argv.index("--min-rate") + 1])
        ok, n = out["total"]
        if 100 * ok / n < need:
            print(f"FAILED: {100 * ok / n:.1f}% passed, at least {need}% required")
            sys.exit(1)

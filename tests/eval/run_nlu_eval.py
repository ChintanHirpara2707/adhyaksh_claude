"""NLU evaluation: action polarity, exact slots and negation. Run: python tests/eval/run_nlu_eval.py [--label X]

Cases are in tests/eval/nlu_cases.csv (hand-written, five language styles, not taken from the training templates):

* polarity: minimal pairs (open / close, create / delete, set / cancel, read / write) on the same target. A pair
  passes only when BOTH members call the right tool with the right argument, so a system that always says "open"
  scores zero instead of 50 percent.
* slots: the argument that reaches the tool must equal the normalised gold value (case-insensitive), not a raw
  sentence: "please open the notepad app for me" -> open_app("notepad").
* negation: "don't open notepad", "notepad mat kholo" and so on. No tool may be called at all.

A positive case may make read-only lookups (READ_ONLY) before its action; any other extra call fails it.

Runs offline through engine.handle_message with every tool mocked (the same mocks as the other evals). Writes
tests/eval/nlu_results.csv and docs/NLU_EVAL.md, and appends to tests/eval/nlu_history.csv.
Optional gates for CI: --min-polarity, --min-slots, --min-negation (percent).
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(ROOT))

from tests.eval import run_eval as base  # noqa: E402

CASES = ROOT / "tests" / "eval" / "nlu_cases.csv"
RESULTS = ROOT / "tests" / "eval" / "nlu_results.csv"
HISTORY = ROOT / "tests" / "eval" / "nlu_history.csv"
REPORT = ROOT / "docs" / "NLU_EVAL.md"
SUITES = ("polarity", "slots", "negation")
IGNORED_CALLS = {"ingest_bytes"}
# Read-only lookups a command may make before its action (cancelling a reminder lists them first). They never
# count against a positive case; a negated request may not call anything at all.
READ_ONLY = {"reminder_list", "recall", "source_list", "process_list", "status", "perf_report", "temp_scan"}


def _norm(value) -> str:
    return " ".join(str(value).replace("\\", "/").strip().strip("\"'").casefold().split())


def check(row: dict) -> dict:
    from adhyaksh.chat import context, engine
    base.CALL_ARGS.clear()
    base.CALL_DETAIL.clear()
    try:
        res = engine.handle_message(row["text"], context.new_conversation())
        data = res.data if res.ok else {"intent": "error", "reply": res.message}
    except Exception as exc:  # a crash is a failure, not an abort
        data = {"intent": "crash", "reply": f"{type(exc).__name__}: {exc}"}
    called = [(name, args) for name, args in base.CALL_DETAIL if name not in IGNORED_CALLS]
    names = [n for n, _ in called]
    want = row["expect_tool"]
    problem = ""
    if want == "none":
        if called:
            problem = f"a negated request ran {names}"
    else:
        actions = [(n, a) for n, a in called if n not in READ_ONLY or n == want]
        if [n for n, _ in actions] != [want]:
            problem = f"expected {want}, called {names or 'nothing'}"
        elif row["expect_arg"]:
            # One expected value, or several separated by "|" for tools with more arguments ("set|speaker|40").
            want_args = [_norm(a) for a in row["expect_arg"].split("|")]
            got = [_norm(a) for a in actions[0][1][:len(want_args)]]
            if got != want_args:
                problem = f"arguments {got or '(none)'}, expected {want_args}"
        called = actions
    return {**row, "intent": data.get("intent", ""), "called": ";".join(names),
            "arg": str(called[0][1][0]) if called and called[0][1] else "", "reply": (data.get("reply") or "")[:120],
            "pass": "PASS" if not problem else "FAIL", "problem": problem}


def score(results: list[dict]) -> dict[str, tuple[int, int]]:
    out: dict[str, tuple[int, int]] = {}
    pairs: dict[str, list[bool]] = defaultdict(list)
    for r in results:
        if r["suite"] == "polarity":
            pairs[r["pair"]].append(r["pass"] == "PASS")
    out["polarity"] = (sum(all(v) for v in pairs.values()), len(pairs))
    for suite in ("slots", "negation"):
        rows = [r for r in results if r["suite"] == suite]
        out[suite] = (sum(r["pass"] == "PASS" for r in rows), len(rows))
    return out


def by_language(results: list[dict]) -> dict[str, tuple[int, int]]:
    agg: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in results:
        agg[r["language"]][0] += r["pass"] == "PASS"
        agg[r["language"]][1] += 1
    return {k: (v[0], v[1]) for k, v in sorted(agg.items())}


def run(label: str = "") -> dict[str, tuple[int, int]]:
    with CASES.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    base.build_env()
    calls: list[str] = []
    patches = base.mocked_tools(calls)
    for p in patches:
        p.start()
    try:
        results = [check(r) for r in rows]
    finally:
        for p in patches:
            p.stop()
    with RESULTS.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(results[0]))
        w.writeheader()
        w.writerows(results)
    scores = score(results)
    stamp = time.strftime("%Y-%m-%d %H:%M")
    new_file = not HISTORY.exists()
    with HISTORY.open("a", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        if new_file:
            w.writerow(["time", "label"] + list(SUITES))
        w.writerow([stamp, label] + [f"{scores[s][0]}/{scores[s][1]}" for s in SUITES])
    write_report(results, scores, stamp, label)
    for s in SUITES:
        a, b = scores[s]
        unit = "pairs" if s == "polarity" else "cases"
        print(f"  {s:9s} {a:3d}/{b:<3d} {unit:5s} {100 * a / b if b else 0:5.1f}%")
    return scores


def write_report(results, scores, stamp, label) -> None:
    L = ["# NLU evaluation (polarity, slots, negation)", "",
         f"Latest run: {stamp}" + (f" ({label})" if label else "") + ". Offline path, every tool mocked. "
         "Cases: tests/eval/nlu_cases.csv. A polarity pair passes only when both of its commands pass.", "",
         "| Suite | Passed | Rate |", "|---|---|---|"]
    for s in SUITES:
        a, b = scores[s]
        L.append(f"| {s} | {a}/{b} {'pairs' if s == 'polarity' else 'cases'} | {100 * a / b if b else 0:.1f}% |")
    L += ["", "Per language (individual commands):", "", "| Language | Passed |", "|---|---|"]
    for lang, (a, b) in by_language(results).items():
        L.append(f"| {lang} | {a}/{b} |")
    fails = [r for r in results if r["pass"] != "PASS"]
    L += ["", f"## Failures ({len(fails)})", ""]
    if fails:
        L += ["| Id | Language | Text | Problem |", "|---|---|---|---|"]
        L += [f"| {r['id']} | {r['language']} | {r['text']} | {r['problem']} |" for r in fails]
    else:
        L.append("None.")
    REPORT.write_text("\n".join(L) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="")
    for s in SUITES:
        ap.add_argument(f"--min-{s}", type=float, default=None, help=f"fail when the {s} rate is below this percent")
    args = ap.parse_args()
    scores = run(args.label)
    failed = []
    for s in SUITES:
        gate = getattr(args, f"min_{s}")
        a, b = scores[s]
        if gate is not None and b and 100 * a / b < gate:
            failed.append(f"{s} {100 * a / b:.1f}% < {gate}%")
    if failed:
        print("GATE FAILED: " + "; ".join(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

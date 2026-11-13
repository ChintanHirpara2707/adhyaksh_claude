"""Train and compare the three intent models.

CLI: python -m adhyaksh.nlu.train --all
Training never runs inside a chat request. The UI starts it through start_background().
"""
from __future__ import annotations

import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from adhyaksh import config, db
from adhyaksh.nlu import dataset, evaluate, models, registry


@dataclass
class EvalSummary:
    name: str
    kind: str
    status: str = "ok"  # ok or "skipped: reason"
    val_macro_f1: float = 0.0
    test_accuracy: float = 0.0
    test_macro_f1: float = 0.0
    codemixed_macro_f1: float = 0.0
    per_language: dict = field(default_factory=dict)
    tau: float = 0.60
    size_bytes: int = 0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    train_seconds: float = 0.0
    model_id: int = 0


def train_all(seed: int = 42, progress=None, kinds=None, write_report: bool = True) -> list[EvalSummary]:
    say = progress or (lambda msg: None)
    errors = dataset.validate()
    if errors:
        raise ValueError("Dataset validation failed: " + "; ".join(errors))
    db.init()
    df, dtest = dataset.load(), dataset.load(dataset.TEST_CSV)
    train, val, test = dataset.split(df, seed)
    dhash = dataset.dataset_hash()
    labels = sorted(dataset.INTENTS)
    out_dir = config.models_dir()
    results: list[tuple[EvalSummary, object]] = []
    for kind in (kinds or list(models.KINDS)):
        s = EvalSummary(models.KINDS[kind], kind)
        say(f"Training {s.name}")
        t0 = time.perf_counter()
        try:
            m = models.make(kind, seed)
            m.fit(train["text"], train["intent"], val_texts=val["text"], val_labels=val["intent"])
        except ImportError as exc:
            s.status = f"skipped: {exc}"
            say(f"Skipped {s.name}: {exc}")
            results.append((s, None))
            continue
        s.train_seconds = time.perf_counter() - t0
        classes = m.classes_
        pv = m.predict_proba(val["text"])
        s.val_macro_f1 = evaluate.compute_metrics(val["intent"], [classes[i] for i in pv.argmax(1)],
                                                  val["language"], labels)["macro_f1"]
        s.tau = evaluate.tune_tau(pv, val["intent"], classes)
        pt = m.predict_proba(test["text"])
        tm = evaluate.compute_metrics(test["intent"], [classes[i] for i in pt.argmax(1)], test["language"], labels)
        pc = m.predict_proba(dtest["text"])
        cm = evaluate.compute_metrics(dtest["intent"], [classes[i] for i in pc.argmax(1)], dtest["language"], labels,
                                      present_only=True)
        s.test_accuracy, s.test_macro_f1, s.per_language = tm["accuracy"], tm["macro_f1"], tm["per_language"]
        s.codemixed_macro_f1 = cm["macro_f1"]
        path = m.save(out_dir)
        s.size_bytes = path.stat().st_size
        s.p50_ms, s.p95_ms = evaluate.measure_latency(m, test["text"])
        s.model_id = registry.register(s.name, kind, path, dhash, {
            "accuracy": s.test_accuracy, "macro_f1": s.test_macro_f1, "size_bytes": s.size_bytes,
            "p50_ms": s.p50_ms, "p95_ms": s.p95_ms, "confusion_json": json.dumps({"labels": labels, "matrix": tm["confusion"]}),
            "per_language_json": json.dumps({"per_language": s.per_language, "codemixed_macro_f1": s.codemixed_macro_f1,
                                             "val_macro_f1": s.val_macro_f1, "tau": s.tau,
                                             "train_seconds": round(s.train_seconds, 2), "seed": seed})})
        results.append((s, m))
        say(f"Finished {s.name}: test macro-F1 {s.test_macro_f1:.3f}")
    ok = [s for s, _ in results if s.status == "ok"]
    if ok:
        best = max(ok, key=lambda s: s.val_macro_f1)  # selected on validation, never on test
        registry.set_active(best.model_id)
        config.set_value("confidence_threshold", str(best.tau))
    if write_report:
        evaluate.write_results_md()
    return [s for s, _ in results]


_POOL = ThreadPoolExecutor(max_workers=1)
_STATE = {"running": False, "log": [], "error": "", "last_started": 0.0}
_LOCK = threading.Lock()


def start_background(seed: int = 42, debounce_s: float = 2.0) -> bool:
    """Queue a training run. Returns False if one is already running or was just started."""
    with _LOCK:
        if _STATE["running"] or time.time() - _STATE["last_started"] < debounce_s:
            return False
        _STATE.update(running=True, log=[], error="", last_started=time.time())

    def job():
        try:
            train_all(seed, progress=lambda m: _STATE["log"].append(m))
        except Exception as exc:
            _STATE["error"] = str(exc)
        finally:
            _STATE["running"] = False

    _POOL.submit(job)
    return True


def status() -> dict:
    return {"running": _STATE["running"], "log": list(_STATE["log"]), "error": _STATE["error"]}


def main(argv: list[str]) -> int:
    if "--all" not in argv:
        print("Usage: python -m adhyaksh.nlu.train --all")
        return 2
    t0 = time.perf_counter()
    for s in train_all(progress=print):
        print(f"{s.name:40s} {s.status:8s} val_f1={s.val_macro_f1:.3f} test_f1={s.test_macro_f1:.3f} "
              f"codemixed_f1={s.codemixed_macro_f1:.3f} tau={s.tau} p95={s.p95_ms:.1f}ms size={s.size_bytes // 1024}KB")
    print(f"total {time.perf_counter() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

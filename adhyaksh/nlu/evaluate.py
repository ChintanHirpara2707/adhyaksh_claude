"""Metrics, latency, confidence-threshold tuning and the results report.

CLI: python -m adhyaksh.nlu.evaluate   (rewrites docs/RESULTS.md from the database)
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np

from adhyaksh import config, db


def compute_metrics(y_true, y_pred, langs, labels, present_only: bool = False) -> dict:
    """Accuracy, macro-F1, per-language macro-F1 and the confusion matrix.

    present_only=True averages macro-F1 over the intents that occur in y_true. Use it for a test file that does
    not cover every intent: labels with no examples would otherwise score 0 and cap the result."""
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score

    y_true, y_pred, langs = list(y_true), list(y_pred), np.array(langs)
    full_labels = list(labels)
    if present_only:
        labels = [lab for lab in labels if lab in set(y_true)]
    per_lang = {}
    for lang in sorted(set(langs)):
        m = langs == lang
        per_lang[lang] = float(f1_score(np.array(y_true)[m], np.array(y_pred)[m], average="macro",
                                        labels=labels, zero_division=0))
    return {"accuracy": float(accuracy_score(y_true, y_pred)),
            "macro_f1": float(f1_score(y_true, y_pred, average="macro", labels=labels, zero_division=0)),
            "per_language": per_lang,
            "confusion": confusion_matrix(y_true, y_pred, labels=full_labels).tolist(), "labels": full_labels}


def measure_latency(model, texts, n: int = 200) -> tuple[float, float]:
    """p50 and p95 latency in ms for single-text prediction with the model already loaded."""
    sample = (list(texts) * (n // max(1, len(texts)) + 1))[:n]
    model.predict_proba(sample[:1])  # warm-up
    times = []
    for t in sample:
        s = time.perf_counter()
        model.predict_proba([t])
        times.append((time.perf_counter() - s) * 1000)
    return float(np.percentile(times, 50)), float(np.percentile(times, 95))


def tune_tau(proba: np.ndarray, y_true, classes, floor: float = 0.30, ceil: float = 0.90) -> float:
    """Smallest threshold whose accepted validation predictions are at least 97 percent correct
    while keeping at least 80 percent coverage. Falls back to the 0.60 default."""
    pred = np.array(classes)[proba.argmax(1)]
    conf, y = proba.max(1), np.array(y_true)
    for tau in np.arange(floor, ceil + 1e-9, 0.05):
        accepted = conf >= tau
        if accepted.mean() >= 0.80 and (pred[accepted] == y[accepted]).mean() >= 0.97:
            return round(float(tau), 2)
    return 0.60


def latest_runs() -> list[dict]:
    return db.query_all(
        "SELECT m.id AS model_id, m.name, m.kind, m.dataset_hash, m.trained_at, m.is_active, e.* "
        "FROM eval_runs e JOIN model_registry m ON m.id=e.model_id "
        "WHERE e.id IN (SELECT MAX(id) FROM eval_runs GROUP BY model_id) ORDER BY m.kind")


def write_results_md(path=None) -> str:
    from adhyaksh.nlu import dataset

    path = path or config.ROOT / "docs" / "RESULTS.md"
    runs = latest_runs()
    lines = ["# Model results", "",
             "All figures come from the latest training run. Dataset: synthetic and UNREVIEWED; "
             "see docs/DATA_CARD.md. The held-out split shares template families with the training "
             "split, so the in-distribution score is optimistic. The code-mixed file uses different "
             "wording and is the harder, more honest figure.", ""]
    if not runs:
        lines.append("No models trained yet. Run: python -m adhyaksh.nlu.train --all")
    else:
        lines += ["| Model | Active | Val macro-F1 | Test accuracy | Test macro-F1 | Code-mixed macro-F1 | tau | Size KB | p50 ms | p95 ms |",
                  "|---|---|---|---|---|---|---|---|---|---|"]
        for r in runs:
            x = json.loads(r["per_language_json"])
            lines.append(f"| {r['name']} | {'yes' if r['is_active'] else 'no'} | {x['val_macro_f1']:.3f} | "
                         f"{r['accuracy']:.3f} | {r['macro_f1']:.3f} | {x['codemixed_macro_f1']:.3f} | {x['tau']} | "
                         f"{r['size_bytes'] / 1024:.0f} | {r['p50_ms']:.2f} | {r['p95_ms']:.2f} |")
        lines += ["", "Per-language test macro-F1:", "", "| Model | " + " | ".join(dataset.LANGS) + " |",
                  "|---|" + "---|" * len(dataset.LANGS)]
        for r in runs:
            pl = json.loads(r["per_language_json"])["per_language"]
            lines.append(f"| {r['name']} | " + " | ".join(f"{pl.get(l, float('nan')):.3f}" for l in dataset.LANGS) + " |")
        best = max(runs, key=lambda r: r["macro_f1"])
        lines += ["", f"Dataset hash: {runs[0]['dataset_hash']}. Target macro-F1 0.85: best test macro-F1 is "
                      f"{best['macro_f1']:.3f} ({'reached' if best['macro_f1'] >= 0.85 else 'NOT reached'})."]
    lines += ["", "## Dataset balance", "", "```", dataset.balance_report(), "```", ""]
    text = "\n".join(lines)
    from pathlib import Path
    Path(path).write_text(text, encoding="utf-8")
    return text


def main() -> int:
    db.init()
    print(write_results_md())
    return 0


if __name__ == "__main__":
    sys.exit(main())

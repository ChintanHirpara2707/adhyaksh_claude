"""Factorised intent check: an ACTION head and a TARGET head trained beside the flat intent model.

Every action intent is a pair (action, target): app_close = (close, app), reminder_cancel = (delete, reminder).
Two small TF-IDF + logistic-regression heads learn the action and the target type from the same training rows.
At prediction time the flat intent is cross-checked: when both heads are confident and together name a different
intent, the request is ambiguous and is NOT dispatched to the nearest intent (the caller asks, uses the agent, or
says it cannot do it). This catches opposite-action mistakes the flat model makes on wording it has not seen.

Without trained heads (an older install) the check does nothing.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from adhyaksh import config

FACTORS: dict[str, tuple[str, str]] = {
    "app_open": ("open", "app"), "app_close": ("close", "app"),
    "file_create": ("create", "file"), "file_delete": ("delete", "file"), "file_read": ("read", "file"),
    "file_update": ("update", "file"), "file_search": ("search", "file"), "folder_create": ("create", "folder"),
    "reminder_set": ("create", "reminder"), "reminder_cancel": ("delete", "reminder"), "reminder_list": ("read", "reminder"),
    "clipboard_read": ("read", "clipboard"), "clipboard_write": ("write", "clipboard"),
    "process_kill": ("close", "process"), "process_list": ("read", "process"),
    "source_delete": ("delete", "source"), "source_list": ("read", "source"), "source_summary": ("summarize", "source"),
}
assert len(set(FACTORS.values())) == len(FACTORS), "every intent needs its own (action, target) pair"
COMPOSE: dict[tuple[str, str], str] = {v: k for k, v in FACTORS.items()}
NONE = "none"
MIN_HEAD_CONF = 0.6
FILES = {"action": "factor_action.joblib", "target": "factor_target.joblib"}
_LOCK = threading.Lock()
_CACHE: dict = {"key": None, "heads": None}


def labels_for(intents) -> tuple[list[str], list[str]]:
    pairs = [FACTORS.get(i, (NONE, NONE)) for i in intents]
    return [a for a, _ in pairs], [t for _, t in pairs]


def train(train_df, val_df, test_df, codemixed_df, out_dir: Path | None = None, seed: int = 42) -> dict:
    """Fit both heads, save them, and return macro-F1 per head on validation, test and the code-mixed file."""
    import joblib
    from sklearn.metrics import f1_score

    from adhyaksh.nlu import models

    out_dir = Path(out_dir or config.models_dir())
    report = {}
    for i, head in enumerate(("action", "target")):
        m = models.make("m1_logreg", seed)
        m.fit(train_df["text"], labels_for(train_df["intent"])[i])
        joblib.dump(m.pipe, out_dir / FILES[head])
        scores = {}
        for name, df in (("val", val_df), ("test", test_df), ("codemixed", codemixed_df)):
            gold = labels_for(df["intent"])[i]
            pred = list(m.pipe.predict(list(df["text"])))
            scores[name] = round(float(f1_score(gold, pred, average="macro", zero_division=0)), 3)
        report[head] = scores
    (out_dir / "factor_report.json").write_text(json.dumps(report), encoding="utf-8")
    reload()
    return report


def reload() -> None:
    with _LOCK:
        _CACHE.update(key=None, heads=None)


def _heads():
    out_dir = Path(config.models_dir())
    paths = {h: out_dir / f for h, f in FILES.items()}
    if not all(p.exists() for p in paths.values()):
        return None
    key = tuple((str(p), p.stat().st_mtime) for p in paths.values())
    with _LOCK:
        if _CACHE["key"] != key:
            import joblib
            _CACHE.update(key=key, heads={h: joblib.load(p) for h, p in paths.items()})
        return _CACHE["heads"]


def heads_say(text: str) -> tuple[str, float, str, float] | None:
    """(action, confidence, target, confidence) from the heads, or None without trained heads."""
    heads = _heads()
    if heads is None:
        return None
    out = []
    for h in ("action", "target"):
        proba = heads[h].predict_proba([text])[0]
        j = int(proba.argmax())
        out += [heads[h].classes_[j], float(proba[j])]
    return out[0], out[1], out[2], out[3]


def cross_check(text: str, intent: str) -> tuple[bool, str]:
    """(agree, note). Disagreement only when both heads are confident and together name another known intent."""
    if intent not in FACTORS:
        return True, ""
    said = heads_say(text)
    if said is None:
        return True, ""
    action, pa, target, pt = said
    composed = COMPOSE.get((action, target))
    if composed and composed != intent and pa >= MIN_HEAD_CONF and pt >= MIN_HEAD_CONF:
        return False, f"flat model said {intent}; action and target heads say {composed}"
    return True, ""


def report() -> dict:
    p = Path(config.models_dir()) / "factor_report.json"
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}

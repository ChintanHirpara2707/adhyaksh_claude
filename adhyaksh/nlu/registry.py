"""Model registry (SQLite) and the cached prediction entry point used by the chat engine."""
from __future__ import annotations

import threading
from pathlib import Path

import numpy as np

from adhyaksh import config, db
from adhyaksh.nlu import models

_LOCK = threading.Lock()
_CACHE: dict = {"id": None, "model": None}

# Reject a prediction when the gap between the top two intents is smaller than this.
# An ambiguous (small-gap) prediction must not fall through to the nearest intent.
MIN_GAP = 0.10


def register(name: str, kind: str, path: Path, dataset_hash: str, eval_row: dict) -> int:
    mid = db.execute("INSERT INTO model_registry(name,kind,path,dataset_hash,trained_at,is_active) "
                     "VALUES(?,?,?,?,?,0)", (name, kind, str(path), dataset_hash, db.utcnow()))
    db.execute("INSERT INTO eval_runs(model_id,accuracy,macro_f1,per_language_json,confusion_json,"
               "size_bytes,p50_ms,p95_ms,created_at) VALUES(?,?,?,?,?,?,?,?,?)",
               (mid, eval_row["accuracy"], eval_row["macro_f1"], eval_row["per_language_json"],
                eval_row["confusion_json"], eval_row["size_bytes"], eval_row["p50_ms"], eval_row["p95_ms"],
                db.utcnow()))
    return mid


def set_active(model_id: int) -> None:
    db.execute("UPDATE model_registry SET is_active=0")
    db.execute("UPDATE model_registry SET is_active=1 WHERE id=?", (model_id,))
    config.set_value("active_model", str(model_id))
    reload()


def active_model_row() -> dict | None:
    return db.query_one("SELECT * FROM model_registry WHERE is_active=1 ORDER BY id DESC LIMIT 1")


def reload() -> None:
    with _LOCK:
        _CACHE.update(id=None, model=None)


def _load_active():
    row = active_model_row()
    if row is None or not Path(row["path"]).exists():
        return None
    with _LOCK:
        if _CACHE["id"] != row["id"]:
            _CACHE.update(id=row["id"], model=models.load(row["kind"], Path(row["path"])))
        return _CACHE["model"]


def available() -> bool:
    return _load_active() is not None


def predict(text: str) -> tuple[str, float, float]:
    """Return (intent, confidence, gap_to_second). Without a trained active model returns
    ('unknown', 0.0, 0.0). The gap is confidence minus the second-best probability."""
    model = _load_active()
    if model is None:
        return "unknown", 0.0, 0.0
    proba = model.predict_proba([text])[0]
    order = np.argsort(proba)[::-1]
    top = float(proba[order[0]])
    second = float(proba[order[1]]) if len(order) > 1 else 0.0
    return model.classes_[order[0]], top, top - second

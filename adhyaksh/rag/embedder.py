"""Local text embeddings for document search (optional).

Uses fastembed (ONNX, CPU) with a small multilingual model when the package is installed AND the model files are
already in models/embeddings. Nothing is downloaded automatically: download() is called only from the Settings
page. When the local model is not available the retriever falls back to Gemini embeddings (consent and key) or to
offline TF-IDF.
"""
from __future__ import annotations

import threading

from adhyaksh import config

METHOD = "local"
_MODEL = {"name": None, "obj": None}
_LOCK = threading.Lock()


def model_name() -> str:
    return config.get("embedding_local_model")


def cache_dir():
    d = config.models_dir() / "embeddings"
    d.mkdir(parents=True, exist_ok=True)
    return d


def installed() -> bool:
    try:
        import fastembed  # noqa: F401
        return True
    except Exception:
        return False


def model_present() -> bool:
    """True when the model files are on disk (any non-empty model folder in the cache)."""
    key = model_name().split("/")[-1].lower()
    for p in cache_dir().glob("models--*"):
        if key in p.name.lower() and any(f.suffix == ".onnx" for f in p.rglob("*.onnx")):
            return True
    return False


def available() -> bool:
    return config.get("embeddings_local") != "off" and installed() and model_present()


def _load(local_only: bool = True):
    with _LOCK:
        if _MODEL["obj"] is None or _MODEL["name"] != model_name():
            from fastembed import TextEmbedding
            _MODEL["obj"] = TextEmbedding(model_name(), cache_dir=str(cache_dir()), local_files_only=local_only)
            _MODEL["name"] = model_name()
        return _MODEL["obj"]


def download() -> tuple[bool, str]:
    """Fetch the model files (about 240 MB) into models/embeddings. Called only on the user's request."""
    if not installed():
        return False, "The fastembed package is not installed. Run: pip install fastembed"
    try:
        _MODEL["obj"] = None
        _load(local_only=False)
        return True, "Embedding model is ready."
    except Exception as exc:  # network or disk problems
        return False, f"The model could not be downloaded ({type(exc).__name__}). Check the internet connection and free disk space."


def embed(texts: list[str]):
    """Unit-length float32 vectors, one row per text."""
    import numpy as np

    model = _load()
    vecs = np.asarray(list(model.embed(list(texts))), dtype="float32")
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    return vecs / np.maximum(norms, 1e-9)

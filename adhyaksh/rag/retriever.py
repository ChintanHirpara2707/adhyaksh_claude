"""Retrieval: TF-IDF cosine (offline) or Gemini embeddings (key and consent), by numpy."""
from __future__ import annotations

from adhyaksh import config, db

_EXTRA_STOP = {"document", "documents", "pdf", "file", "files", "say", "says", "said", "according", "search",
               "find", "mention", "mentioned", "mein", "ke", "ka", "ki", "baare", "kya", "hai", "likha", "ma",
               "ni", "vishe", "shu", "che", "lakhyu", "mujab", "mere", "mera", "meri", "mara", "mari"}
_CACHE: dict = {"sig": None, "vec": None, "matrix": None, "rows": None}


def embedding_mode() -> str:
    """'gemini' only with provider gemini, a key and cloud consent; otherwise offline 'tfidf'."""
    from adhyaksh.llm import base
    if config.get_bool("cloud_consent") and config.get("llm_provider") == "gemini" and base.api_key("gemini"):
        return "gemini"
    return "tfidf"


def _rows() -> list[dict]:
    return db.query_all("SELECT c.id, c.text, c.page_or_section AS location, c.embedding, d.filename "
                        "FROM doc_chunks c JOIN documents d ON d.id=c.document_id ORDER BY c.id")


def _tfidf_index(rows):
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
    from adhyaksh.nlu.features import TOKEN_PATTERN
    sig = (len(rows), rows[-1]["id"] if rows else 0)
    if _CACHE["sig"] != sig:
        vec = TfidfVectorizer(token_pattern=TOKEN_PATTERN, sublinear_tf=True, ngram_range=(1, 2),
                              stop_words=list(ENGLISH_STOP_WORDS | _EXTRA_STOP))
        _CACHE.update(sig=sig, vec=vec, matrix=vec.fit_transform([r["text"] for r in rows]), rows=rows)
    return _CACHE["vec"], _CACHE["matrix"]


def retrieve(question: str, k: int = 4) -> list[dict]:
    """Top-k chunks with score; each hit has text, filename, location, score."""
    rows = _rows()
    if not rows:
        return []
    scores = None
    if embedding_mode() == "gemini" and all(r["embedding"] for r in rows):
        try:
            import numpy as np
            from adhyaksh.llm.gemini import embed
            q = np.asarray(embed([question])[0], dtype="float32")
            m = np.vstack([np.frombuffer(r["embedding"], dtype="float32") for r in rows])
            scores = (m @ q) / (np.linalg.norm(m, axis=1) * np.linalg.norm(q) + 1e-9)
        except Exception:
            scores = None
    if scores is None:
        from sklearn.metrics.pairwise import linear_kernel
        vec, matrix = _tfidf_index(rows)
        scores = linear_kernel(vec.transform([question]), matrix).ravel()
    order = scores.argsort()[::-1][:k]
    return [{"text": rows[i]["text"], "filename": rows[i]["filename"], "location": rows[i]["location"],
             "score": float(scores[i])} for i in order]

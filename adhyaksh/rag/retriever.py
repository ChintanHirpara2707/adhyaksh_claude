"""Retrieval inside one notebook: local embeddings (fastembed), Gemini embeddings (key and consent) or offline TF-IDF.

Each notebook has its own index, so a question is only ever answered from the sources of the active notebook.
"""
from __future__ import annotations

from adhyaksh import config, db

_EXTRA_STOP = {"document", "documents", "pdf", "file", "files", "say", "says", "said", "according", "search",
               "find", "mention", "mentioned", "mein", "ke", "ka", "ki", "baare", "kya", "hai", "likha", "ma",
               "ni", "vishe", "shu", "che", "lakhyu", "mujab", "mere", "mera", "meri", "mara", "mari"}
_CACHE: dict = {}  # notebook id -> {"sig", "vec", "matrix"}


def embedding_mode() -> str:
    """'local' when the local embedding model is ready; 'gemini' only with provider gemini, a key and cloud
    consent; otherwise offline 'tfidf'."""
    from adhyaksh.llm import base
    from adhyaksh.rag import embedder
    if embedder.available():
        return "local"
    if config.get_bool("cloud_consent") and config.get("llm_provider") == "gemini" and base.api_key("gemini"):
        return "gemini"
    return "tfidf"


def _rows(notebook_id: int) -> list[dict]:
    return db.query_all("SELECT c.id, c.text, c.page_or_section AS location, c.embedding, c.method, d.filename, d.id AS doc_id "
                        "FROM doc_chunks c JOIN documents d ON d.id=c.document_id WHERE d.notebook_id=? ORDER BY c.id",
                        (notebook_id,))


def _tfidf_index(rows, notebook_id):
    from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS, TfidfVectorizer
    from adhyaksh.nlu.features import TOKEN_PATTERN
    # The signature includes the database path and a little of the text, so an index is never reused for other content.
    sig = (str(config.db_path()), len(rows), rows[-1]["id"], hash(rows[0]["text"][:80] + rows[-1]["text"][-80:])) if rows else ()
    cached = _CACHE.get(notebook_id)
    if cached is None or cached["sig"] != sig:
        vec = TfidfVectorizer(token_pattern=TOKEN_PATTERN, sublinear_tf=True, ngram_range=(1, 2),
                              stop_words=list(ENGLISH_STOP_WORDS | _EXTRA_STOP))
        cached = {"sig": sig, "vec": vec, "matrix": vec.fit_transform([r["text"] for r in rows])}
        _CACHE[notebook_id] = cached
    return cached["vec"], cached["matrix"]


def retrieve(question: str, k: int = 4, notebook_id: int | None = None) -> list[dict]:
    """Top-k chunks of one notebook; each hit has text, filename, location, score and the method used."""
    if notebook_id is None:
        from adhyaksh.rag import sources
        notebook_id = sources.active_id()
    rows = _rows(notebook_id)
    if not rows:
        return []
    scores, method = None, "tfidf"
    mode = embedding_mode()
    if mode in ("local", "gemini") and all(r["embedding"] and r["method"] == mode for r in rows):
        try:
            import numpy as np
            if mode == "local":
                from adhyaksh.rag import embedder
                q = embedder.embed([question])[0]
            else:
                from adhyaksh.llm.gemini import embed
                q = np.asarray(embed([question])[0], dtype="float32")
            m = np.vstack([np.frombuffer(r["embedding"], dtype="float32") for r in rows])
            scores = (m @ q) / (np.linalg.norm(m, axis=1) * np.linalg.norm(q) + 1e-9)
            method = mode
        except Exception:
            scores = None
    if scores is None:
        from sklearn.metrics.pairwise import linear_kernel
        vec, matrix = _tfidf_index(rows, notebook_id)
        scores = linear_kernel(vec.transform([question]), matrix).ravel()
    order = scores.argsort()[::-1][:k]
    return [{"text": rows[i]["text"], "filename": rows[i]["filename"], "location": rows[i]["location"],
             "score": float(scores[i]), "method": method} for i in order]

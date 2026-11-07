"""Answer questions from indexed documents with citations. Extractive offline; LLM only with consent."""
from __future__ import annotations

from adhyaksh import config, responses
from adhyaksh.llm import base
from adhyaksh.rag import retriever
from adhyaksh.result import Result


def answer(question: str) -> Result:
    hits = retriever.retrieve(question)
    threshold = config.get_float("doc_min_score")
    good = [h for h in hits if h["score"] >= threshold]
    if not good:
        return Result.success({"answer": responses.t("doc_not_found"), "sources": [], "mode": "none", "found": False})
    sources = [{"file": h["filename"], "location": h["location"], "score": round(h["score"], 3)} for h in good]
    if config.get_bool("cloud_consent") and base.get_provider() is not None:
        passages = "\n\n".join(f"[{h['filename']}, {h['location']}] {h['text']}" for h in good)
        res = base.ask("Answer the question using only the passages below. If they do not contain the answer, "
                       f"say it is not found in the documents.\n\nPassages:\n{passages}\n\nQuestion: {question}")
        if res.ok:
            return Result.success({"answer": res.data, "sources": sources, "mode": "llm", "found": True})
    text = "\n\n".join(f"{h['text']}\n(Source: {h['filename']}, {h['location']})" for h in good[:3])
    return Result.success({"answer": text, "sources": sources, "mode": "extractive", "found": True})

"""Notebook-style sources: per-notebook index, citations, summaries, per-source delete, embeddings."""
import os
import sqlite3
from pathlib import Path

import numpy as np
import pytest

from adhyaksh import config, db
from adhyaksh.chat import context, engine, router
from adhyaksh.rag import answerer, embedder, loader, retriever, sources
from adhyaksh.result import E_NEEDS_CONFIRM
from tests.helpers import fresh_env

REAL_MODELS = Path(__file__).resolve().parent.parent / "models"
WARRANTY = b"The warranty period for the mixer is two years from the date of purchase. Keep the bill safe."
RECIPE = b"To cook rice, wash one cup of rice, add two cups of water and boil for fifteen minutes."


def test_migration_adds_notebooks_and_keeps_old_documents(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.executescript(db.SCHEMA_V1 + "PRAGMA user_version=1;")
    conn.execute("INSERT INTO documents(filename,filepath,pages,indexed_at,status) VALUES('a.txt','x',1,'t','indexed')")
    conn.commit()
    conn.close()
    assert db.init(path) == db.MIGRATIONS[-1][0]
    conn = sqlite3.connect(path)
    assert conn.execute("SELECT name FROM notebooks WHERE id=1").fetchone()[0] == "General"
    assert conn.execute("SELECT notebook_id FROM documents WHERE filename='a.txt'").fetchone()[0] == 1
    conn.close()


def test_each_notebook_answers_only_from_its_own_sources():
    fresh_env()
    assert sources.active()["name"] == "General"
    loader.ingest_bytes("warranty.txt", WARRANTY)
    nb = sources.create_notebook("Cooking").data
    assert sources.active_id() == nb["id"] and sources.count() == 0
    loader.ingest_bytes("rice.txt", RECIPE)
    assert answerer.answer("how long should rice boil").data["found"]
    assert not answerer.answer("what is the warranty period of the mixer").data["found"]  # other notebook
    sources.set_active(1)
    a = answerer.answer("what is the warranty period of the mixer").data
    assert a["found"] and "two years" in a["answer"]
    assert not answerer.answer("how long should rice boil").data["found"]
    assert [n["sources"] for n in sources.list_notebooks()] == [1, 1]
    assert sources.create_notebook("cooking").data["existing"]  # same name, no duplicate


def test_answers_carry_numbered_citations():
    fresh_env()
    loader.ingest_bytes("warranty.txt", WARRANTY)
    a = answerer.answer("what is the warranty period").data
    assert "[1]" in a["answer"] and "Sources:\n[1] warranty.txt, Section 1" in a["answer"]
    assert a["sources"][0] == {"n": 1, "file": "warranty.txt", "location": "Section 1", "score": a["sources"][0]["score"]}


def test_source_list_summary_and_delete_through_chat():
    fresh_env()
    cid = context.new_conversation()
    say = lambda t, **k: engine.handle_message(t, cid, **k).data  # noqa: E731
    r = say("give me a summary of this file", attachments=[("warranty.txt", WARRANTY)])
    assert r["intent"] == "source_summary" and "warranty.txt" in r["reply"] and "two years" in r["reply"]
    say("", attachments=[("rice.txt", RECIPE)])
    r = say("which sources have i added")
    assert r["intent"] == "source_list" and "2 source(s)" in r["reply"] and "rice.txt" in r["reply"]
    r = say("summarize all my sources")
    assert r["intent"] == "source_summary" and "rice.txt" in r["reply"] and "warranty.txt" in r["reply"]
    r = say("remove the source rice.txt")
    assert r["intent"] == "source_delete" and r["confirmation"]["action"] == "source_delete" and sources.count() == 2
    r = say("yes")
    assert "Removed the source rice.txt" in r["reply"] and [s["filename"] for s in loader.list_documents(1)] == ["warranty.txt"]
    assert "No source named" in say("remove the source nothing.pdf")["reply"]
    assert sources.delete_source("warranty.txt").error_code == E_NEEDS_CONFIRM  # never without confirmation


def test_extractive_summary_keeps_the_main_sentences():
    text = ("The annual report covers sales in Gujarat. Sales in Gujarat grew by twelve percent. The weather was pleasant. "
            "Growth in Gujarat sales came from the new Surat branch. A cat sat outside. The Surat branch opened in March.")
    s = sources.extractive_summary(text, max_sentences=3)
    assert "Sales in Gujarat grew" in s and "cat" not in s and s.startswith("The annual report")
    assert sources.extractive_summary("short") == "short"


@pytest.mark.parametrize("text,intent,name", [
    ("show the sources of this notebook", "source_list", None), ("what files are in my notebook", "source_list", None),
    ("mere sources dikhao", "source_list", None), ("drop tax.pdf from my sources", "source_delete", "tax.pdf"),
    ("delete the source old notes.docx", "source_delete", "old notes.docx"),
    ("give me the gist of the attached document", "source_summary", None), ("summarize report.pdf", "source_summary", "report.pdf"),
    ("इस फाइल का सार बताओ", "source_summary", None),
])
def test_source_rules(text, intent, name):
    r = router.understand(text)
    assert r is not None and r.intent == intent and (name is None or r.slots.get("name") == name), (text, r)


@pytest.mark.parametrize("text", ["summarize the French revolution", "delete notes.txt", "what does the attachment say about fees",
                                  "show my downloads folder"])
def test_source_rules_do_not_hijack(text):
    r = router.match_sources(text)
    assert r is None, (text, r)


def test_fake_embeddings_are_stored_and_used(monkeypatch):
    fresh_env()

    def fake_embed(texts):
        out = []
        for t in texts:
            v = np.zeros(64, dtype="float32")
            for w in t.lower().split():
                v[hash(w.strip(".,?")) % 64] += 1.0
            out.append(v / max(np.linalg.norm(v), 1e-9))
        return np.vstack(out)
    monkeypatch.setattr(embedder, "available", lambda: True)
    monkeypatch.setattr(embedder, "embed", fake_embed)
    res = loader.ingest_bytes("warranty.txt", WARRANTY)
    assert res.data["method"] == "local" and retriever.embedding_mode() == "local"
    hits = retriever.retrieve("warranty period for the mixer")
    assert hits[0]["method"] == "local" and hits[0]["score"] > config.get_float("doc_min_score_embed")
    assert answerer.answer("warranty period for the mixer").data["found"]
    # if the model disappears, search still works offline with TF-IDF
    monkeypatch.setattr(embedder, "available", lambda: False)
    assert retriever.retrieve("warranty period")[0]["method"] == "tfidf"


def test_embedder_never_downloads_by_itself():
    fresh_env()  # empty temporary models folder
    assert not embedder.model_present() and not embedder.available() and retriever.embedding_mode() == "tfidf"


@pytest.mark.skipif(not any((REAL_MODELS / "embeddings").glob("models--*")) or not embedder.installed(),
                    reason="local embedding model not downloaded")
def test_real_multilingual_embeddings_find_a_paraphrase_in_another_language(monkeypatch):
    fresh_env()
    monkeypatch.setenv("ADHYAKSH_MODELS_DIR", str(REAL_MODELS))
    embedder._MODEL.update(name=None, obj=None)
    assert embedder.available()
    loader.ingest_bytes("warranty.txt", WARRANTY)
    loader.ingest_bytes("rice.txt", RECIPE)
    a = answerer.answer("मिक्सर की गारंटी कितने साल की है").data  # Hindi question, English source, no shared words
    assert a["found"] and a["sources"][0]["file"] == "warranty.txt"
    assert not answerer.answer("who won the football world cup").data["found"]

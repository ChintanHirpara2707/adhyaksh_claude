import os
import time

from adhyaksh import config
from adhyaksh.llm import base as llm
from adhyaksh.rag import answerer, chunker, loader, retriever
from adhyaksh.result import E_BLOCKED, E_NO_API_KEY
from tests.helpers import fresh_env

TOPICS = {
    "Introduction": "This report describes the Harbor Lights solar microgrid pilot in the village of Ravpur.",
    "Budget": "The total approved budget for the pilot is 4.2 million rupees, split between panels, batteries and training.",
    "Deadline": "The installation deadline is 30 June 2027 and the commissioning review follows in July.",
    "Methodology": "Engineers surveyed 120 households and measured daily load using smart meters over six weeks.",
    "Safety": "All batteries must be stored in ventilated cabinets and technicians must wear insulated gloves.",
    "Findings": "The main finding is that evening demand peaks at 7 pm and exceeds solar output without storage.",
}


def _sample_docx(path, pad_sections=0):
    from docx import Document
    d = Document()
    for head, body in TOPICS.items():
        d.add_heading(head, level=1)
        d.add_paragraph(body)
    for i in range(pad_sections):
        d.add_heading(f"Appendix {i}", level=1)
        d.add_paragraph(" ".join(f"filler{i}x{j}" for j in range(120)))
    d.save(path)


def test_chunker_bounds_and_overlap():
    text = " ".join(f"w{i}" for i in range(600))
    chunks = chunker.chunk_text(text)
    assert len(chunks) > 3 and all(len(c) <= 500 for c in chunks)
    assert chunks[0].split()[-1] in chunks[1].split()  # overlap
    assert chunker.chunk_text("   ") == [] and chunker.chunk_text("short") == ["short"]


def test_ingest_validation():
    d = fresh_env()
    bad = d / "x.exe"
    bad.write_text("x")
    assert not loader.ingest(str(bad)).ok and not loader.ingest(str(d / "missing.txt")).ok
    empty = d / "e.txt"
    empty.write_text("   ")
    assert not loader.ingest(str(empty)).ok


def test_docx_qa_with_citations_and_not_found():
    d = fresh_env()
    f = d / "pilot.docx"
    _sample_docx(f)
    res = loader.ingest(str(f))
    assert res.ok and res.data["chunks"] >= 6
    for question, needle, section in [
        ("what is the approved budget", "4.2 million", "Budget"),
        ("when is the installation deadline", "30 June 2027", "Deadline"),
        ("how many households were surveyed", "120 households", "Methodology"),
        ("how should batteries be stored", "ventilated cabinets", "Safety"),
        ("when does evening demand peak", "7 pm", "Findings")]:
        a = answerer.answer(question).data
        assert a["found"] and needle in a["answer"], question
        assert a["sources"][0]["file"] == "pilot.docx" and a["sources"][0]["location"] == section, question
    for unrelated in ("what is the capital of Mongolia", "who won the cricket world cup"):
        a = answerer.answer(unrelated).data
        assert not a["found"] and a["answer"] == "Not found in your documents.", unrelated


def test_txt_ingest_and_delete():
    d = fresh_env()
    f = d / "n.txt"
    f.write_text("Quarterly revenue grew twelve percent because of the new Surat branch.", encoding="utf-8")
    r = loader.ingest(str(f))
    assert answerer.answer("why did revenue grow").data["found"]
    assert loader.delete_document(r.data["id"]).ok and not answerer.answer("why did revenue grow").data["found"]


def test_indexing_speed_for_large_document():
    d = fresh_env()
    f = d / "big.docx"
    _sample_docx(f, pad_sections=40)  # roughly the volume of a 20-page document
    t = time.perf_counter()
    r = loader.ingest(str(f))
    assert r.ok and time.perf_counter() - t < 30
    print("indexed", r.data["chunks"], "chunks in", round(time.perf_counter() - t, 2), "s")


def test_llm_requires_consent_and_key():
    fresh_env()
    for var in ("GROQ_API_KEY", "GEMINI_API_KEY"):
        os.environ.pop(var, None)
    assert llm.ask("hi").error_code == E_BLOCKED
    config.set_value("cloud_consent", "true")
    assert llm.ask("hi").error_code == E_NO_API_KEY
    assert llm.mask("abcd1234wxyz") == "********wxyz" and llm.get_provider() is None
    assert retriever.embedding_mode() == "tfidf"

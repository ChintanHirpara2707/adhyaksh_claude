"""Document ingestion: PDF (PyMuPDF), DOCX (python-docx) and TXT into chunks stored in SQLite."""
from __future__ import annotations

import shutil
import time
from pathlib import Path

from adhyaksh import config, db
from adhyaksh.rag.chunker import chunk_text
from adhyaksh.result import E_ACTION_FAILED, E_FILE_NOT_FOUND, Result
from adhyaksh.tools.files import sanitize_name

MAX_BYTES = 25 * 1024 * 1024
EXTENSIONS = {".pdf", ".docx", ".txt"}


def _sections(text: str, size: int = 2000) -> list[tuple[str, str]]:
    return [(f"Section {i + 1}", text[s:s + size]) for i, s in enumerate(range(0, len(text), size)) if text[s:s + size].strip()]


def extract(path: Path) -> list[tuple[str, str]]:
    """Return (location label, text) units for a file."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        import fitz  # PyMuPDF
        with fitz.open(path) as pdf:
            return [(f"page {i + 1}", page.get_text()) for i, page in enumerate(pdf)]
    if ext == ".docx":
        from docx import Document
        units, label, buf = [], "Section 1", []
        for p in Document(path).paragraphs:
            if p.style is not None and p.style.name.lower().startswith("heading") and p.text.strip():
                if buf:
                    units.append((label, "\n".join(buf)))
                label, buf = p.text.strip(), []
            elif p.text.strip():
                buf.append(p.text)
        if buf:
            units.append((label, "\n".join(buf)))
        if len(units) <= 1:
            return _sections("\n".join(t for _, t in units))
        return units
    return _sections(path.read_text(encoding="utf-8", errors="replace"))


def ingest(path: str) -> Result:
    src = Path(path)
    if not src.is_file():
        return Result.failure(E_FILE_NOT_FOUND, "The file was not found.")
    if src.suffix.lower() not in EXTENSIONS:
        return Result.failure(E_ACTION_FAILED, "Only PDF, DOCX and TXT files are supported.")
    if src.stat().st_size > MAX_BYTES:
        return Result.failure(E_ACTION_FAILED, "The file is larger than 25 MB.")
    try:
        name = sanitize_name(src.name)
    except ValueError as exc:
        return Result.failure(E_ACTION_FAILED, str(exc))
    dest = config.uploads_dir() / f"{int(time.time() * 1000)}_{name}"
    try:
        shutil.copyfile(src, dest)
        units = extract(dest)
    except ImportError as exc:
        dest.unlink(missing_ok=True)
        return Result.failure(E_ACTION_FAILED, f"A required library is missing: {exc.name}.")
    except Exception as exc:  # corrupt or unreadable document
        dest.unlink(missing_ok=True)
        return Result.failure(E_ACTION_FAILED, f"The document could not be read ({type(exc).__name__}).")
    chunks = [(label, c) for label, text in units for c in chunk_text(text)]
    if not chunks:
        dest.unlink(missing_ok=True)
        return Result.failure(E_ACTION_FAILED, "The document contains no readable text.")
    doc_id = db.execute("INSERT INTO documents(filename,filepath,pages,indexed_at,status) VALUES(?,?,?,?,?)",
                        (name, str(dest), len(units), db.utcnow(), "indexed"))
    blobs: list[bytes | None] = [None] * len(chunks)
    method = "tfidf"
    from adhyaksh.rag import retriever
    if retriever.embedding_mode() == "gemini":
        try:
            import numpy as np
            from adhyaksh.llm.gemini import embed
            blobs = [np.asarray(v, dtype="float32").tobytes() for v in embed([c for _, c in chunks])]
            method = "gemini"
        except Exception:  # fall back to offline TF-IDF retrieval
            blobs, method = [None] * len(chunks), "tfidf"
    db.executemany("INSERT INTO doc_chunks(document_id,chunk_index,page_or_section,text,embedding,method) VALUES(?,?,?,?,?,?)",
                   [(doc_id, i, label, text, blobs[i], method) for i, (label, text) in enumerate(chunks)])
    return Result.success({"id": doc_id, "filename": name, "units": len(units), "chunks": len(chunks), "method": method})


def list_documents() -> list[dict]:
    return db.query_all("SELECT d.*, (SELECT COUNT(*) FROM doc_chunks c WHERE c.document_id=d.id) AS chunks "
                        "FROM documents d ORDER BY d.id DESC")


def delete_document(doc_id: int) -> Result:
    row = db.query_one("SELECT filepath FROM documents WHERE id=?", (doc_id,))
    if row is None:
        return Result.failure(E_FILE_NOT_FOUND, "The document is not indexed.")
    db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
    Path(row["filepath"]).unlink(missing_ok=True)
    return Result.success()


def ingest_bytes(name: str, data: bytes) -> Result:
    """Ingest an uploaded file held in memory."""
    import tempfile
    if len(data) > MAX_BYTES:
        return Result.failure(E_ACTION_FAILED, "The file is larger than 25 MB.")
    try:
        name = sanitize_name(Path(name).name)
    except ValueError as exc:
        return Result.failure(E_ACTION_FAILED, str(exc))
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / name
        p.write_bytes(data)
        return ingest(str(p))

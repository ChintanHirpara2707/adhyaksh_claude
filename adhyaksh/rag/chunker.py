"""Split text into overlapping chunks of about 500 characters on whitespace boundaries."""
from __future__ import annotations


def chunk_text(text: str, size: int = 500, overlap: int = 100) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    if len(text) <= size:
        return [text]
    chunks, start = [], 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind(" ", start + size // 2, end)
            end = cut if cut != -1 else end
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        nxt = text.rfind(" ", start, max(start + 1, end - overlap))
        start = nxt + 1 if nxt > start else end
    return [c for c in chunks if c]

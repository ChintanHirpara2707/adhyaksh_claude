"""Name extraction and the single operator profile."""
from __future__ import annotations

import re
import unicodedata

from adhyaksh import db

STOP = {"ready", "fine", "good", "great", "okay", "ok", "sure", "happy", "sad", "tired", "hungry", "busy",
        "here", "back", "your", "you", "the", "a", "an", "new", "not", "very", "so", "also", "student",
        "assistant", "sorry", "glad", "late", "later", "now", "going", "coming", "just", "still", "from", "in",
        "on", "at", "with", "and", "or", "but", "hai", "che", "hoon", "chu", "है", "हूँ", "छે", "છે", "છું",
        "bulao", "kaho", "bolo", "कहो", "કહો", "doing", "well", "bored", "confused", "working", "learning",
        "trying", "looking", "user", "owner", "friend", "boss", "master"}
_ROLES = r"(?:user|owner|master|boss|friend|creator|developer|admin|operator)"
EXPLICIT = [
    r"\b(?:my name is|my name's|you can call me|call me)\s+(.+)$",
    rf"\bi am your (?:new )?{_ROLES}\s+(.+)$",
    r"\bmera naam\s+(.+?)\s+hai\b", r"\bmujhe\s+(.+?)\s+(?:bulao|kaho|bolo)\b",
    r"\bmain aapka (?:naya )?user\s+(.+?)\s+hoon\b",
    r"\bmaru naam\s+(.+?)\s+che\b", r"\bmane\s+(.+?)\s+kaho\b", r"\bhu tamaro (?:navo )?user\s+(.+?)\s+chu\b",
    r"मेरा नाम\s+(.+?)\s+है", r"मुझे\s+(.+?)\s+कहो", r"मैं आपका (?:नया )?उपयोगकर्ता\s+(.+?)\s+हूँ",
    r"મારું નામ\s+(.+?)\s+છે", r"મને\s+(.+?)\s+કહો", r"હું તમારો (?:નવો )?વપરાશકર્તા\s+(.+?)\s+છું",
]
BARE = r"^(?:i am|i'm|im)\s+(.+)$"
_HYPOTHETICAL = re.compile(r"\b(?:when|if|suppose|imagine|say|maybe|perhaps)\b", re.IGNORECASE)
_QUOTED = re.compile(r"[\"'\u201c\u2018].+?[\"'\u201d\u2019]")
_MULTI_NAME = re.compile(r"\bmy name is\s+(.+?)(?=\s+my name is|\s*$)", re.IGNORECASE)


def _is_word(tok: str) -> bool:
    return 2 <= len(tok) <= 20 and all(ch.isalpha() or unicodedata.category(ch).startswith("M") for ch in tok)


def _name(raw: str, require_caps: bool) -> str | None:
    out = []
    for tok in re.split(r"\s+", raw.strip().strip(".,!?।")):
        tok = tok.strip(".,!?।")
        if not _is_word(tok) or tok.casefold() in STOP:
            break
        if require_caps and tok.isascii() and not tok[0].isupper():
            break
        out.append(tok)
        if len(out) == 3:
            break
    if not out:
        return None
    return " ".join(t.title() if t.isascii() else t for t in out)


def extract_name(text: str) -> tuple[str | None, float]:
    """Return (name, confidence).

    Confidence 0.95 for an explicit single declaration (auto-saved), 0.7 for a corrected/declared
    name that needs confirmation, 0.55 for a bare 'I am X' or a hypothetical/quoted phrase (ask
    first, never auto-save).
    """
    t = text.strip()
    hypothetical = bool(_HYPOTHETICAL.search(t)) or bool(_QUOTED.search(t))

    # Disambiguate "my name is not X, my name is Y": use the last declared name.
    segments = list(_MULTI_NAME.finditer(t))
    if len(segments) > 1:
        name = _name(segments[-1].group(1), require_caps=False)
        if name:
            return name, 0.7

    for pat in EXPLICIT:
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            name = _name(m.group(1), require_caps=False)
            if name:
                conf = 0.55 if hypothetical else 0.95
                return name, conf
    m = re.match(BARE, t, re.IGNORECASE)
    if m:
        name = _name(m.group(1), require_caps=True)
        if name:
            return name, 0.55
    return None, 0.0


def save_name(name: str) -> None:
    if db.query_one("SELECT id FROM profile WHERE id=1"):
        db.execute("UPDATE profile SET display_name=? WHERE id=1", (name,))
    else:
        db.execute("INSERT INTO profile(id,display_name,created_at) VALUES(1,?,?)", (name, db.utcnow()))


def get_name() -> str | None:
    row = db.query_one("SELECT display_name FROM profile WHERE id=1")
    return row["display_name"] if row else None

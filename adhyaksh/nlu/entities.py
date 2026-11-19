"""Entity extraction: one place that turns words in a request into clean, normalised tool arguments.

Every extractor returns a canonical value (an allow-list app key, a bare file name, a full URL), never a raw
sentence. Used by the frame parser (nlu/frames.py), the rule router and the engine, so the same entity is read the
same way on every path.
"""
from __future__ import annotations

import difflib
import re
import urllib.parse
from functools import lru_cache

from adhyaksh.nlu import lexicon

FILE_EXTENSIONS = ("txt", "pdf", "docx", "doc", "xlsx", "xls", "csv", "pptx", "png", "jpg", "jpeg", "py", "md",
                   "zip", "json")
FILE_RE = re.compile(r"((?:[A-Za-z]:)?[\w\-./\\ऀ-ॿ઀-૿]*[\w\-ऀ-ॿ઀-૿]"
                     r"\.[A-Za-z0-9]{1,5})(?![\w])")
_QUOTED = re.compile(r"[\"'“‘]([^\"'”’]+)[\"'”’]")
_FUZZY_CUTOFF = 0.85
_NOT_APPS = {"open", "close", "start", "stop", "point", "print", "page", "paste", "code", "note", "notes", "pad",
             "edge", "explore", "calendar", "crime", "chore", "home", "remote", "photo", "photos"}


def _bounded(spelling: str, text: str) -> re.Match | None:
    return re.search(rf"(?<![\wऀ-ॿ઀-૿]){re.escape(spelling)}(?![\wऀ-ॿ઀-૿])", text)


def app_spellings() -> list[tuple[str, str]]:
    """(spelling, canonical key) for every known app: the lexicon, the user's allow-list and the tool's aliases,
    longest spelling first so 'google chrome' wins over 'chrome' and 'visual studio code' over 'code'."""
    from adhyaksh.tools import apps
    pairs: dict[str, str] = {}
    for key, spellings in lexicon.APP_NAMES.items():
        for s in spellings:
            pairs[s.casefold()] = key
    for alias, key in apps.ALIASES.items():
        pairs.setdefault(alias.casefold(), key)
    for key in apps.allowlist():
        pairs.setdefault(key.casefold(), key)
    return sorted(pairs.items(), key=lambda kv: len(kv[0]), reverse=True)


# One-word spellings that are also everyday words: they name an app only when nothing else in the request could
# be the object ("open code" is VS Code; "my locker code is 4417" and "run python code" are not).
GENERIC_SPELLINGS = {"code", "calc", "explorer", "edge"}


@lru_cache(maxsize=1)
def _command_words() -> frozenset[str]:
    """Single words a command may contain besides its object. Multi-word verb forms ("what is on", "turn up") are
    removed as whole phrases first (_strip_verb_phrases): their parts alone ("what", "is") are not command words."""
    words = {v.casefold() for by_lang in lexicon.ACTIONS.values() for verbs in by_lang.values() for v in verbs if " " not in v}
    words |= {w.casefold() for ws in lexicon.FILLERS.values() for f in ws for w in f.split()}
    words |= {w.casefold() for by_lang in lexicon.TARGET_NOUNS.values() for ws in by_lang.values() for w in ws if " " not in w}
    words |= {w.casefold() for ws in lexicon.NEGATION.values() for n in ws for w in n.split()}
    return frozenset(words | {"to", "it", "up", "app", "on", "off", "and", "me", "this", "that"})


@lru_cache(maxsize=1)
def _verb_phrases() -> tuple[str, ...]:
    phrases = {v.casefold() for by_lang in lexicon.ACTIONS.values() for verbs in by_lang.values() for v in verbs if " " in v}
    phrases |= {w.casefold() for by_lang in lexicon.TARGET_NOUNS.values() for ws in by_lang.values() for w in ws if " " in w}
    return tuple(sorted(phrases, key=len, reverse=True))


def _strip_verb_phrases(low: str) -> str:
    for p in _verb_phrases():
        low = re.sub(rf"(?<!\w){re.escape(p)}(?!\w)", " ", low)
    return low


def _only_object(spelling: str, low: str) -> bool:
    rest = _strip_verb_phrases(re.sub(rf"(?<!\w){re.escape(spelling)}(?!\w)", " ", low))
    return all(w in _command_words() for w in re.findall(r"[\w']+", rest))


def find_app(text: str, *, fuzzy: bool = False) -> str | None:
    """The canonical app key named in the text ('please open the note pad' -> 'notepad'), or None.
    With fuzzy=True, a near spelling of a Latin name also counts ('notpad', 'calculater')."""
    low = " ".join((text or "").casefold().split())
    for spelling, key in app_spellings():
        if len(spelling) >= 3 and _bounded(spelling, low):
            if spelling in GENERIC_SPELLINGS and not _only_object(spelling, low):
                continue
            return key
    if not fuzzy:
        return None
    latin = {s: k for s, k in app_spellings() if s.isascii() and len(s) >= 5 and " " not in s}
    words = re.findall(r"[a-z]{4,}", low)
    grams = words + [f"{a} {b}" for a, b in zip(words, words[1:])]
    for tok in grams:
        if tok in _NOT_APPS:
            continue
        close = difflib.get_close_matches(tok.replace(" ", ""), list(latin), n=1, cutoff=_FUZZY_CUTOFF)
        if close:
            return latin[close[0]]
    return None


def find_file(text: str) -> str | None:
    """A quoted name with an extension (may contain spaces), a 'called X.ext' name with spaces, or the first
    path-like token with an extension. Returns the name as written (no surrounding punctuation)."""
    q = _QUOTED.search(text or "")
    if q and "." in q.group(1):
        return q.group(1).strip()
    named = re.search(r"\b(?:called|named|naam(?:\s+ki|\s+ni|\s+nu)?|titled)\s+(?P<n>[^\s].*?\.(?:"
                      + "|".join(FILE_EXTENSIONS) + r"))(?![\w])", text or "", re.IGNORECASE)
    if named and len(named.group("n").split()) <= 4:
        return named.group("n").strip()
    m = FILE_RE.search(text or "")
    if not m:
        return None
    name = m.group(1).rstrip(".")
    if re.fullmatch(r"(?:www\.)?[\w-]+\.(?:com|in|org|net|io|ai|dev|co|edu|gov)", name, re.IGNORECASE):
        return None  # a website, not a file
    return name


def has_file_extension(text: str) -> bool:
    return find_file(text) is not None


def named(text: str) -> str | None:
    """The name after 'named', 'called' or 'naam ki/ka/nu' ('files named invoice' -> 'invoice')."""
    m = re.search(r"\b(?:named|called|titled)\s+(?P<n>[\w\-. ]+?)[\s.!?]*$", text or "", re.IGNORECASE)
    if m:
        return m.group("n").strip()
    m = re.search(r"(?P<n>[\w\-.]+)\s+(?:naam\s+(?:ki|ka|ke|ni|nu|no)|नाम\s+(?:की|का|के)|નામ(?:ની|નું|નો))\b", text or "", re.IGNORECASE)
    return m.group("n").strip() if m else None


_URL = re.compile(r"\bhttps?://[^\s<>\"']+|(?<![@\w.])(?:[a-z0-9-]+\.)+(?:com|in|org|net|io|ai|dev|co|edu|gov|info|me|app|uk|wiki)"
                  r"(?:/[^\s<>\"']*)?(?![\w])", re.IGNORECASE)


def find_url(text: str) -> str | None:
    """A web address in the text ('https://example.com/a', 'github.com/user/repo'), normalised, else None.
    Email addresses are not web addresses."""
    m = _URL.search(text or "")
    return normalize_url(m.group(0)) if m else None


def normalize_url(url: str) -> str:
    """'github.com' -> 'https://github.com'; keeps an explicit http(s) scheme and the path; lower-cases the host."""
    u = (url or "").strip().strip("\"'<>").rstrip(".,!?;")
    if not u:
        return u
    if not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.IGNORECASE):
        u = "https://" + u
    parts = urllib.parse.urlsplit(u)
    return urllib.parse.urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, parts.fragment))


_DIGITS = str.maketrans("०१२३४५६७८९૦૧૨૩૪૫૬૭૮૯", "01234567890123456789")
_NUMBER = re.compile(r"(?<![\w.])(\d{1,3})(?:\s*(?:%|percent|per\s*cent|pratishat|takka|taka|टका|प्रतिशत|ટકા))?(?![\w.])",
                     re.IGNORECASE)


def number(text: str) -> int | None:
    """The first whole number 0-100 in the text, in any script ('volume 40%', 'आवाज़ ४० करो' -> 40), else None."""
    m = _NUMBER.search((text or "").translate(_DIGITS))
    if not m:
        return None
    n = int(m.group(1))
    return n if 0 <= n <= 100 else None


def system_target(text: str) -> tuple[str, tuple[int, int]] | None:
    """A system target named by a noun ('volume', 'माइक', 'brightness') and its span, else None."""
    low = (text or "").casefold()
    for kind in lexicon.SYSTEM_TARGETS:
        words = sorted({w.casefold() for ws in lexicon.TARGET_NOUNS[kind].values() for w in ws}, key=len, reverse=True)
        for w in words:
            m = _bounded(w, low)
            if m:
                return kind, m.span()
    return None


_PROCESS_STOP = {"for", "of", "the", "process", "task", "program", "app", "please", "now"}


def clean_process_target(target: str) -> str:
    """'for notepad.exe' -> 'notepad.exe'; a process name never keeps leading prepositions or filler."""
    words = [w for w in (target or "").split() if w.casefold() not in _PROCESS_STOP]
    return " ".join(words).strip(" ,.")

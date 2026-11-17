"""Text rules for spoken input: yes/no answers in five language styles, wake words, transcript cleanup.

Used by the chat engine (spoken confirmations) and by the chat page for audio transcribed on this laptop.
"""
from __future__ import annotations

import re

_YES = ["yes", "yeah", "yep", "yup", "y", "sure", "ok", "okay", "confirm", "confirmed", "do it", "go ahead", "proceed", "please do",
        "yes please", "yes do it", "of course", "correct", "right", "haan", "haa", "han", "ha", "haan ji", "ha ji", "ji haan", "ji",
        "theek hai", "thik hai", "kar do", "kardo", "karo", "chalega", "bilkul", "hoy", "hoye", "haa ji", "barabar", "kari do",
        "हाँ", "हां", "हा", "जी", "जी हाँ", "हाँ जी", "ठीक है", "कर दो", "बिल्कुल", "હા", "હા જી", "જી", "બરાબર", "કરી દો", "ચોક્કસ"]
_NO = ["no", "nope", "nah", "n", "cancel", "stop", "dont", "don't", "do not", "no thanks", "not now", "leave it", "never mind",
       "nevermind", "abort", "nahi", "nahin", "na", "mat karo", "rehne do", "rahne do", "mat", "nako", "nathi", "bilkul nahi",
       "nai", "na re", "rehva do", "rehva de", "cancel karo", "cancel kar do", "નહીં", "ના", "રહેવા દો", "નથી", "કેન્સલ",
       "नहीं", "ना", "मत करो", "रहने दो", "कैंसिल", "रद्द करो"]
_FILLER = re.compile(r"^(?:(?:ok|okay|hmm|umm|uh|well|so|ji)\s+)+|(?:\s+(?:please|pls|now|ji|bhai|yaar|ne|re))+$", re.IGNORECASE)
_PUNCT = re.compile(r"[.,!?;:\"'()।]+")


def _norm(text: str) -> str:
    return " ".join(_PUNCT.sub(" ", str(text or "")).casefold().split())


_YES_SET = {_norm(w) for w in _YES}
_NO_SET = {_norm(w) for w in _NO}


def yes_no(text: str) -> bool | None:
    """True for a clear yes, False for a clear no, None when it is neither (a new request, or unclear).

    Accepts short answers with filler ("yes please do it", "haan kar do", "ના રહેવા દો"); a longer sentence
    that merely contains "yes" is not an answer."""
    t = _norm(text)
    if not t:
        return None
    core = _FILLER.sub("", t).strip() or t
    for cand in (t, core):
        if cand in _YES_SET:
            return True
        if cand in _NO_SET:
            return False
    words = core.split()
    if len(words) <= 4:
        first2, first1 = " ".join(words[:2]), words[0]
        if first2 in _NO_SET or first1 in _NO_SET:
            return False
        if (first2 in _YES_SET or first1 in _YES_SET) and not any(w in _NO_SET for w in words[1:]):
            return True
    return None


DEFAULT_WAKE = ["adhyaksh", "adhyaksha", "adyaksh", "hey assistant", "अध्यक्ष", "અધ્યક્ષ"]
_LEAD = re.compile(r"^(?:hey|hi|ok|okay|hello|oye|are)\s+", re.IGNORECASE)
_FUZZY_WAKE = re.compile(r"^adh?y[aeiou]?k?(?:sh|s|x|ch)a?$")


def wake_words(setting: str | None) -> list[str]:
    extra = [w.strip() for w in str(setting or "").split(",") if w.strip()]
    seen: dict[str, None] = {}
    for w in extra + DEFAULT_WAKE:
        seen[_norm(w)] = None
    return [w for w in seen if w]


def strip_wake(text: str, words: list[str]) -> tuple[bool, str]:
    """(matched, rest). The wake word must open the phrase; small recogniser spelling slips are tolerated."""
    body = _LEAD.sub("", str(text or "").strip())
    low = _norm(body)
    for w in words:
        if low == w or low.startswith(w + " "):
            n = len(w.split())
            return True, " ".join(body.split()[n:]).lstrip(",.:!- ")
    first = low.split(" ")[0] if low else ""
    if _FUZZY_WAKE.match(first):
        return True, " ".join(body.split()[1:]).lstrip(",.:!- ")
    return False, str(text or "").strip()


_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")
_JOINED = {"note pad": "notepad", "calcu lator": "calculator", "you tube": "youtube", "g mail": "gmail", "whats app": "whatsapp",
           "screen shot": "screenshot", "power point": "powerpoint", "dot txt": ".txt", "dot pdf": ".pdf", "dot docx": ".docx"}


def clean_transcript(text: str) -> str:
    """Tidy a speech-recognition transcript: split words glued in CamelCase ('OpenNotePad'), rejoin known names
    split by the recogniser ('note pad'), and drop a final full stop."""
    t = _CAMEL.sub(" ", str(text or "")).strip()
    low = t.casefold()
    for a, b in _JOINED.items():
        if a in low:
            t = re.sub(re.escape(a), b, t, flags=re.IGNORECASE)
            low = t.casefold()
    t = re.sub(r"\s+\.(txt|pdf|docx)\b", r".\1", t)
    return " ".join(t.split()).rstrip(".")


SPOKEN_CONFIRM = {"en": "Say yes to confirm, or no to cancel.", "hi": "हाँ बोलें तो पुष्टि होगी, ना बोलें तो रद्द होगा।",
                  "gu": "પુષ્ટિ માટે હા કહો, રદ કરવા ના કહો."}


def confirm_prompt(lang_code: str) -> str:
    """Sentence appended to a spoken confirmation question, in the voice language."""
    return SPOKEN_CONFIRM.get((lang_code or "en")[:2], SPOKEN_CONFIRM["en"])

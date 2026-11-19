"""Structured facts: "my locker code is 4417" -> (subject "user", attribute "locker code", value "4417").

The parser understands statements and questions in the five language styles:

    my car is Audi / mera birthday 12 march ko hai / मेरी कार ऑडी है / મારો રૂમ નંબર 204 છે / maro phone number 98 che
    what is my car / mera birthday kab hai / मेरी कार क्या है / મારો રૂમ નંબર શું છે
    forget my car / meri car bhool jao / मेरी कार भूल जाओ / મારી કાર ભૂલી જાઓ

Attributes are normalised (case, articles, possessives, synonyms across languages) so the same attribute said two
ways is one fact: saving it again updates the value instead of adding a contradicting second fact.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

USER = "user"
GENERAL = "general"

# Possessive openers ("my") per language style.
_MY = r"(?:my|mera|meri|mere|maro|mari|maru|mara|मेरा|मेरी|मेरे|મારો|મારી|મારું|મારા)"
# Copulas that end a Hindi/Gujarati statement or join an English one.
_EN_IS = r"(?:is|are|was|=|:|is\s+called|is\s+named)"
_IN_END = r"(?:hai|hain|he|che|chhe|cche|है|हैं|છે)"
# Second words that belong to the attribute, not the value ("phone number", "locker code", "favorite color").
_ATTR_TAIL = {"number", "no", "code", "password", "pin", "id", "name", "naam", "colour", "color", "rang", "day", "din", "date",
              "address", "city", "school", "college", "company", "office", "teacher", "doctor", "food", "movie", "song", "book",
              "team", "plate", "size", "group", "type", "model", "account", "email", "mail", "nambar", "નંબર", "नंबर", "कोड",
              "કોડ", "नाम", "નામ", "रंग", "રંગ", "पासवर्ड", "પાસવર્ડ", "दिन", "દિવસ", "तारीख", "તારીખ"}
# One attribute, many spellings (English, Hinglish, Hindi, Gujarati).
_SYNONYMS = {
    "birthday": ["birthday", "bday", "birth day", "date of birth", "dob", "janamdin", "janmdin", "janmadin", "जन्मदिन",
                 "जन्म दिन", "बर्थडे", "જન્મદિવસ", "જન્મ દિવસ", "બર્થડે"],
    "favorite color": ["favorite color", "favourite colour", "favorite colour", "favourite color", "fav color", "fav colour",
                       "pasandida rang", "pasandeeda rang", "gamto rang", "पसंदीदा रंग", "मनपसंद रंग", "ગમતો રંગ", "મનપસંદ રંગ"],
    "phone number": ["phone number", "mobile number", "phone no", "mobile no", "number", "phone", "mobile", "फोन नंबर",
                     "मोबाइल नंबर", "ફોન નંબર", "મોબાઇલ નંબર"],
    "car": ["car", "gaadi", "gadi", "कार", "गाड़ी", "ગાડી", "કાર"],
    "bike": ["bike", "scooter", "बाइक", "બાઇક"],
    "dog": ["dog", "kutta", "kutro", "कुत्ता", "કૂતરો"],
    "exam": ["exam", "pariksha", "parixa", "परीक्षा", "પરીક્ષા"],
    "room number": ["room number", "room no", "kamra number", "कमरा नंबर", "रूम नंबर", "રૂમ નંબર"],
    "wifi password": ["wifi password", "wi-fi password", "wifi pass", "wifi", "वाईफाई पासवर्ड", "વાઇફાઇ પાસવર્ડ"],
}
_CANON = {variant.casefold(): canon for canon, variants in _SYNONYMS.items() for variant in variants}
_PUNCT = " \t.,!?;:।\"'"


@dataclass(frozen=True)
class Fact:
    subject: str
    attribute: str
    value: str


def normalize_attribute(attr: str) -> str:
    a = " ".join(re.sub(r"[\"'’]s\b", "", attr.casefold()).split()).strip(_PUNCT)
    a = re.sub(r"^(?:the|a|an)\s+", "", a)
    return _CANON.get(a, a)


def _split_attr_value(words: list[str]) -> tuple[str, str] | None:
    """Hindi-style 'X Y hai' has no word between attribute and value: the attribute is one word, or two when the
    second is a typical attribute word ('phone number', 'locker code'), or a known multi-word synonym."""
    if len(words) < 2:
        return None
    for n in (3, 2):
        if len(words) > n and " ".join(words[:n]).casefold() in _CANON:
            return " ".join(words[:n]), " ".join(words[n:])
    n = 2 if len(words) > 2 and words[1].casefold() in _ATTR_TAIL else 1
    return " ".join(words[:n]), " ".join(words[n:])


_EN_STATEMENT = re.compile(rf"^{_MY}\s+(?P<a>.+?)\s+{_EN_IS}\s+(?P<v>.+)$", re.IGNORECASE)
_IN_STATEMENT = re.compile(rf"^{_MY}\s+(?P<rest>.+?)\s+{_IN_END}$", re.IGNORECASE)
_IN_KA = re.compile(rf"^{_MY}\s+(?P<a>.+?)\s+(?:ka|ki|ke|no|ni|nu|का|की|के|નો|ની|નું)\s+(?:naam|name|नाम|નામ)\s+(?P<v>.+?)\s+{_IN_END}$",
                    re.IGNORECASE)


def parse_statement(text: str) -> Fact | None:
    """The structured form of a personal fact, or None when the sentence is not of the form 'my X is Y'."""
    t = " ".join((text or "").split()).strip(_PUNCT)
    m = _IN_KA.match(t)  # "mere dog ka naam Bruno hai" -> dog name = Bruno
    if m:
        return Fact(USER, normalize_attribute(m.group("a") + " name"), m.group("v").strip(_PUNCT))
    m = _EN_STATEMENT.match(t)
    if m and not re.match(r"^(?:not|a\s+secret)\b", m.group("v"), re.IGNORECASE):
        return Fact(USER, normalize_attribute(m.group("a")), m.group("v").strip(_PUNCT))
    m = _IN_STATEMENT.match(t)
    if m:
        split = _split_attr_value(m.group("rest").split())
        if split and split[1]:
            return Fact(USER, normalize_attribute(split[0]), split[1].strip(_PUNCT))
    return None


# Questions: "what is my X", "when is my X", "do you know my X", "mera X kya hai", "મારો X શું છે".
_EN_QUESTION = re.compile(rf"^(?:what|when|where|which|who|how\s+much|how\s+many)(?:'s|\s+is|\s+are|\s+was)?\s+{_MY}\s+(?P<a>.+?)[\s?.!]*$"
                          rf"|^(?:do\s+you\s+(?:know|remember)|tell\s+me|remind\s+me\s+of|recall)\s+{_MY}\s+(?P<a2>.+?)[\s?.!]*$",
                          re.IGNORECASE)
_IN_QUESTION = re.compile(rf"^{_MY}\s+(?P<a>.+?)\s+(?:kya|kab|kahan|kaha|kaun|kitna|kitni|shu|kyare|kya\s+che|kon|ketlo|ketli|"
                          rf"क्या|कब|कहाँ|कहां|कौन|कितना|कितनी|શું|ક્યારે|ક્યાં|કોણ|કેટલો|કેટલી)(?=[\s?.!]|$).*$", re.IGNORECASE)


def question_attribute(text: str) -> str | None:
    """The attribute a question asks about ('when is my birthday' -> 'birthday'), or None."""
    t = " ".join((text or "").split()).strip(_PUNCT)
    m = _EN_QUESTION.match(t)
    if m:
        return normalize_attribute(m.group("a") or m.group("a2"))
    m = _IN_QUESTION.match(t)
    if m:
        return normalize_attribute(m.group("a"))
    return None


# "forget my X", "delete my X from memory", "meri car bhool jao", "मेरी कार भूल जाओ", "મારી કાર ભૂલી જાઓ".
_FORGET = re.compile(
    rf"^(?:please\s+)?(?:forget|erase|remove|delete|clear)\s+(?:about\s+|that\s+)?(?:{_MY}\s+)?(?P<a>.+?)"
    rf"(?:\s+(?:from|in)\s+(?:your\s+|my\s+|the\s+)?memory)?[\s.!]*$"
    rf"|^(?:{_MY}\s+)?(?P<a2>.+?)\s+(?:bhool\s+ja\w*|bhul\s+ja\w*|bhuli\s+ja\w*|bhooli\s+ja\w*|yaad\s+se\s+hata\w*|"
    rf"memory\s+(?:se|mathi)\s+(?:hata|kadhi)\w*(?:\s+\w+)?|भूल\s+जा\w*|याद\s+से\s+हटा\w*|ભૂલી\s+જા\w*|યાદમાંથી\s+કાઢ\w*)[\s.!]*$",
    re.IGNORECASE)
_NOT_FORGET = re.compile(r"^(?:don'?t|do\s+not|never)\s+forget\b", re.IGNORECASE)


def forget_attribute(text: str) -> str | None:
    """The attribute a forget request names, or None. 'Don't forget ...' means remember, never forget."""
    t = " ".join((text or "").split()).strip(_PUNCT)
    if _NOT_FORGET.match(t):
        return None
    m = _FORGET.match(t)
    if not m:
        return None
    a = (m.group("a") or m.group("a2") or "").strip(_PUNCT)
    if not a or re.search(r"\.\w{1,5}$", a):  # "delete notes.txt" is a file, not a memory
        return None
    if m.group("a") and not re.match(r"^(?:please\s+)?forget\b", t, re.IGNORECASE) and not re.search(r"\bmemory\b", t, re.IGNORECASE):
        # "delete my reminders", "remove chrome": delete, remove, erase and clear are memory requests only when they
        # name the memory ("delete my car from memory"); "forget" always is.
        return None
    return normalize_attribute(a)

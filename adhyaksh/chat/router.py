"""Rule layer (greetings, safe math, identity, simple references) and slot extraction."""
from __future__ import annotations

import ast
import operator
import re
import urllib.parse
from dataclasses import dataclass, field

from adhyaksh.chat import identity
from adhyaksh.tools import apps

_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Mod: operator.mod, ast.Pow: operator.pow, ast.FloorDiv: operator.floordiv}
_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def safe_eval(expr: str) -> float:
    """Evaluate plain arithmetic through the ast module. Raises ValueError for anything else."""
    def walk(n):
        if isinstance(n, ast.Expression):
            return walk(n.body)
        if isinstance(n, ast.Constant) and type(n.value) in (int, float):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            a, b = walk(n.left), walk(n.right)
            if isinstance(n.op, ast.Pow) and (abs(b) > 100 or abs(a) > 1e6):
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](a, b)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _UNARY:
            return _UNARY[type(n.op)](walk(n.operand))
        raise ValueError("unsupported expression")
    if len(expr) > 100:
        raise ValueError("expression too long")
    try:
        return walk(ast.parse(expr.strip(), mode="eval"))
    except (SyntaxError, ZeroDivisionError, OverflowError) as exc:
        raise ValueError(str(exc)) from exc


def _extract_math(text: str):
    """Find an arithmetic expression anywhere in the text (not just at the start/end)."""
    for m in re.finditer(r"[\d][\d\s.+\-*/()%^xX×÷]*[\d]|[\d]", text):
        raw = m.group(0).strip()
        expr = raw.replace("×", "*").replace("÷", "/").replace("^", "**")
        expr = re.sub(r"(?<=[\d)\s])[xX](?=[\d(\s])", "*", expr)
        if not re.search(r"\d", expr) or not re.search(r"[+\-*/%^]", expr.lstrip("-")):
            continue
        try:
            value = safe_eval(expr)
            return raw, round(value, 6)
        except ValueError:
            continue
    return None


_WORD_OP_MAP = (
    ("divided by", "/"), ("power", "**"), ("into", "*"), ("times", "*"),
    ("multiplied by", "*"), ("multiplied into", "*"), ("minus", "-"),
    ("plus", "+"), ("का गुणा", "*"), ("घात", "**"), ("गुणा", "*"), ("गुना", "*"),
    ("भाग", "/"), ("माइनस", "-"), ("प्लस", "+"), ("ઘાત", "**"),
    ("ગુણાકાર", "*"), ("ગુણા", "*"), ("ભાગ", "/"), ("માઇનસ", "-"), ("પ્લસ", "+"),
)


def _word_math(text: str):
    """Evaluate word-based arithmetic like '5 plus 7', '6 into 7', '2 power 3'."""
    s = text.casefold()
    for word, sym in _WORD_OP_MAP:
        s = s.replace(word, sym)
    s = re.sub(r"[^0-9.\+\-\*/\(\)\^ ]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    expr = s.replace("^", "**")
    expr = re.sub(r"(?<=[\d)\s])x(?=[\d(\s])", "*", expr)
    if not re.search(r"\d", expr) or not re.search(r"[+\-*/\*\^]", expr.lstrip("-")):
        return None
    try:
        value = safe_eval(expr)
        return expr, round(value, 6)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Web command parsing (shared by the rule path and the model path)
# ---------------------------------------------------------------------------

_WEB_SITES = {
    "github": "github.com",
    "youtube": "youtube.com",
    "gmail": "gmail.com",
    "google": "google.com",
    "linkedin": "linkedin.com",
    "instagram": "instagram.com",
    "facebook": "facebook.com",
    "x": "x.com",
    "twitter": "x.com",
    "whatsapp web": "web.whatsapp.com",
    "maps": "maps.google.com",
}

# Application names that, when used as a standalone "open <name>", should route
# to the app launcher rather than being treated as a website.
_WEB_APPS = {
    "notepad", "calculator", "paint", "excel", "word", "chrome", "edge",
    "brave", "vs code", "vscode", "whatsapp", "spotify", "snipping tool",
    "file explorer", "file manager",
}

# Known file extensions: a token with one of these is a file, never a site.
_FILE_EXTENSIONS = ("txt", "pdf", "docx", "doc", "xlsx", "xls", "csv", "pptx",
                    "png", "jpg", "jpeg", "py", "md", "zip", "json")

# Filler words removed only as whole words at the START of the text.
_LEADING_FILLERS = ("please", "pls", "plz", "can you", "chrome mein", "in chrome")

# Trailing request verbs removed only at the END of the text (longest first).
_TRAILING_VERBS = (
    "khol dena", "kholi do", "kholi de", "khol de", "khar do", "kholo ne", "khol do", "kholo",
    "ખોલો ને", "ખોલો", "karo", "do", "ne",
)

# Search-engine prefixes stripped from the start of a query.
_SEARCH_PREFIXES = ("google par", "par", "on google")

# Markers that make a search request a local file search.
_LOCAL_SEARCH_MARKERS = ("my", "files", "file", "folder", "folders", "drive",
                         "document", "documents")


def _has_file_extension(text: str) -> bool:
    """True if text contains a token with a known file extension."""
    low = text.casefold()
    for ext in _FILE_EXTENSIONS:
        if re.search(rf"\b[\w-]+\.{re.escape(ext)}\b", low):
            return True
    return False


def _normalize_text(text: str) -> str:
    """Normalize text once before routing, for typed and voice input alike.

    Trim, collapse whitespace, strip trailing punctuation, and convert spoken
    ``dot`` forms (``dot com``, ``dot in``, ``dot org``) to ``.``.
    """
    t = " ".join(text.split())
    t = t.strip().rstrip(".!?।")
    t = re.sub(r"\s*dot\s+(com|in|org)\b", r".\1", t, flags=re.IGNORECASE)
    return t


def _strip_leading_fillers(text: str) -> str:
    """Remove leading filler words/phrases (whole words at the start only)."""
    for filler in _LEADING_FILLERS:
        text = re.sub(rf"^{re.escape(filler)}\s+", "", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _strip_trailing_verbs(text: str) -> str:
    """Remove trailing request verbs (e.g. ``karo``, ``kholo``) at the end."""
    for verb in _TRAILING_VERBS:
        text = re.sub(rf"\s+{re.escape(verb)}\s*$", "", text, flags=re.IGNORECASE)
    return " ".join(text.split())


def _strip_search_prefix(query: str) -> str:
    """Strip search-engine prefixes (``google par``, ``par``) from a query."""
    for prefix in _SEARCH_PREFIXES:
        query = re.sub(rf"^{re.escape(prefix)}\s+", "", query, flags=re.IGNORECASE)
    return " ".join(query.split())


def _is_local_search(query: str) -> bool:
    """True if a search request refers to local files/folders rather than Google."""
    low = query.casefold()
    for marker in _LOCAL_SEARCH_MARKERS:
        if re.search(rf"\b{re.escape(marker)}\b", low):
            return True
    return _has_file_extension(query)


def _normalize_site(site: str) -> str | None:
    """Normalize a spoken/typed site name to a URL.

    Known sites are mapped; anything already containing a dot is passed through
    (with an ``https://`` scheme added when missing).
    """
    s = " ".join(site.split())
    s = re.sub(r"\s*dot\s+(com|in|org)\b", r".\1", s, flags=re.IGNORECASE)
    key = s.casefold()
    base = re.sub(r"\.(com|in|org|co\.in)$", "", key, flags=re.IGNORECASE)
    if key in _WEB_SITES:
        return _WEB_SITES[key]
    if base in _WEB_SITES:
        return _WEB_SITES[base]
    if "." in s:
        return s if s.startswith(("http://", "https://")) else "https://" + s
    return None


def parse_web_command(text: str):
    """Parse a web command into a :class:`Rule` with intent ``web_open`` or
    ``file_search``.

    This is the ONE function used by both the rule path and the model path.
    When a web verb is present but no URL/site/query can be extracted, it
    returns ``Rule("web_open", {})`` so the engine can ask a clarifying
    question and keep a pending slot. Returns ``None`` when the text is not a
    web command (for example a file name with an extension).
    """
    t = _normalize_text(text)
    # strip leading fillers ("please search...", "can you open...", "chrome mein open...")
    t = _strip_leading_fillers(t)
    low = t.casefold()

    # "new tab" alone -> default browser at google.
    if re.fullmatch(r"(?:in\s+chrome\s+)?(?:open|go\s+to)?\s*(?:a\s+)?new\s+tab[.!?।]*",
                    t, re.IGNORECASE):
        return Rule("web_open", {"url": "https://www.google.com"})

    # "search google for X (in a new tab)"
    m = re.match(
        r"search\s+google\s+for\s+(?P<query>.+?)(?:\s+in\s+a\s+new\s+tab)?[.!?।]*$",
        t, re.IGNORECASE)
    if m:
        query = " ".join(m.group("query").split())
        query = _strip_trailing_verbs(query)
        query = _strip_search_prefix(query)
        if query:
            return Rule("web_open", {
                "url": "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)})
        return Rule("web_open", {})

    # search (for) X (on google) (in a new tab) -> Google search, unless it
    # mentions files/folders/drive/my or has a file extension (local search).
    m = re.match(
        r"(?:search\s+karo|search(?:\s+for)?|શોધો|शोधो|खोजो)\s+(?P<query>.+?)"
        r"(?:\s+in\s+a\s+new\s+tab)?[.!?।]*$",
        t, re.IGNORECASE)
    if m:
        query = _strip_trailing_verbs(m.group("query"))
        query = _strip_leading_fillers(query)
        query = _strip_search_prefix(query)
        if _is_local_search(query):
            return Rule("file_search", {"query": query})
        if query:
            return Rule("web_open", {
                "url": "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)})
        return Rule("web_open", {})

    # trailing search verb (hinglish): "python search karo", "google par python search karo"
    m = re.match(r"(?P<query>.+?)\s+search\s+karo[.!?।]*$", t, re.IGNORECASE)
    if m:
        query = _strip_trailing_verbs(m.group("query"))
        query = _strip_search_prefix(query)
        if _is_local_search(query):
            return Rule("file_search", {"query": query})
        if query:
            return Rule("web_open", {
                "url": "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)})
        return Rule("web_open", {})

    # open/go to <site> (optional trailing verb: "youtube khol do")
    m = re.match(
        r"(?:open|go\s+to|खोलो\s+ने|खोलो|ખોલો\s+ને|ખોલો)\s+(?P<rest>.+?)"
        r"(?:\s+in\s+a\s+new\s+tab)?[.!?।]*$", t, re.IGNORECASE)
    if m:
        site = re.sub(r"\s+(?:site|website|web\s*page|page|wala|wali)$", "", _strip_trailing_verbs(m.group("rest")),
                      flags=re.IGNORECASE)
        if _has_file_extension(site):
            # A token with a file extension is a file, never a website.
            return None
        site_url = _normalize_site(site)
        if site_url and site_url.casefold() not in _WEB_APPS:
            return Rule("web_open", {"url": site_url})
        # A known application name: defer to the app rule.
        return None

    # <site> <trailing verb> (hinglish/gujlish word order): "youtube kholo",
    # "gmail ખોલો". Only treat as a site if it resolves to a known site or
    # contains a dot, so we never hijack a plain search query.
    m = re.match(
        r"(?P<site>.+?)\s+(?:khol dena|kholi do|kholi de|khol de|khar do|khol do|kholo ne|kholo|ખોલો ને|ખોલો)"
        r"[.!?।]*$", t, re.IGNORECASE)
    if m:
        site_url = _normalize_site(m.group("site"))
        if site_url and site_url.casefold() not in _WEB_APPS:
            return Rule("web_open", {"url": site_url})
        return None

    # Bare web verb with no site/query -> clarifying question.
    if re.match(r"^(open|go\s+to|search|खोलो|खोलो\s+ने|શોધો|खोजो)\s*$", low):
        return Rule("web_open", {})

    return None


def extract_web_url(text: str) -> str | None:
    """Resolve a web URL from arbitrary user text (bare site, search, or command)."""
    rule = parse_web_command(text)
    if rule:
        return rule.slots.get("url")
    site = _normalize_site(text)
    if site:
        return site
    query = " ".join(text.split())
    if query:
        return "https://www.google.com/search?q=" + urllib.parse.quote_plus(query)
    return None


@dataclass
class Rule:
    intent: str
    slots: dict = field(default_factory=dict)


_GREET = re.compile(r"^(hello|hi|hey|namaste|namaskar|good (morning|afternoon|evening)|नमस्ते|नमस्कार|हेलो|हाय|"
                    r"નમસ્તે|કેમ છો|હેલો|kem cho|kem chho|hello assistant)[\s.!]*$", re.IGNORECASE)
_GET_ID = re.compile(r"^(what is my name|who am i|tell me my name|do you know my name|mera naam kya hai|"
                     r"maru naam shu che|मेरा नाम क्या है|મારું નામ શું છે)[\s?.!]*$", re.IGNORECASE)
_MATH = re.compile(r"^\s*(?:what is|what's|calculate|compute|solve)?\s*([\d\s.+\-*/()%^xX×÷]+?)\s*[=?]*\s*$", re.IGNORECASE)
_BOT_ID = re.compile(r"^(?:what is|what's)\s+(?:your\s+)?name[\s?.!]*$|^who\s+are\s+you[\s?.!]*$|^who\s+are\s+u[\s?.!]*$", re.IGNORECASE)
_TIME_DATE = re.compile(r"^(?:what is|what's|tell me|show me|please)?\s*(?:the\s+)?"
                        r"(?P<kind>today'?s?\s*date|current\s*time|the\s*time|the\s*date|time|date)"
                        r"[\s?.!]*$", re.IGNORECASE)
_FILE_CREATE_NAMED = re.compile(
    r"(?:create|make|new)\s+(?:one\s+)?(?:a\s+)?(?:\w*\s+)*file\s+(?:name|named|called)(?:\s+(?:called|named))?\s+(.+?)[\s?.!]*$",
    re.IGNORECASE)
_FOLDER_CREATE = re.compile(
    r"^(?:create|make|new)\s+(?:one\s+)?(?:a\s+)?(?:new\s+)?(?:folder|directory|dir)\s+(?:called|named)\s+(.+?)[\s?.!]*$"
    r"|^(?:folder|directory|dir)\s+(?:बनाओ|बनावो|banaen|बनवा)[\s?.!]*$", re.IGNORECASE)
_SCREENSHOT = re.compile(r"^(?:take|capture)\s+(?:a\s+)?screenshot[\s?.!]*$", re.IGNORECASE)
_SPECIAL_FOLDER = re.compile(
    r"^(?:open)\s+(recycle\s*bin|recyclebin|downloads|documents|desktop|file\s*manager|file\s*explorer|explorer)[\s?.!]*$",
    re.IGNORECASE)
_SMALLTALK = re.compile(
    r"^(thanks|thank you|thanks a lot|bye|goodbye|see you|how are you|how are you doing|"
    r"धन्यवाद|शुक्रिया|अलविदा|ठीक है|कैसा हो|कैसे हो|"
    r"આભાર|અલવિદા|સારાં|કેમ છો)[\s?.!]*$", re.IGNORECASE)
_REF = re.compile(r"^(delete|remove|erase|read|open|show)\s+(it|that|this)(\s+file)?[\s.!]*$", re.IGNORECASE)
_REF_INTENT = {"delete": "file_delete", "remove": "file_delete", "erase": "file_delete", "read": "file_read",
               "open": "file_read", "show": "file_read"}
FILE_RE = re.compile(r"((?:[A-Za-z]:)?[\w\-./\\\u0900-\u097F\u0A80-\u0AFF]*[\w\-\u0900-\u097F\u0A80-\u0AFF]\.[A-Za-z0-9]{1,5})(?![\w])")
_PRONOUN = re.compile(r"\b(it|that|this|isko|ise|use|eno|aene)\b", re.IGNORECASE)


def match_rules(text: str) -> Rule | None:
    t = text.strip()
    if _GREET.match(t):
        return Rule("greet")
    if _GET_ID.match(t):
        return Rule("get_identity")
    if _BOT_ID.match(t):
        return Rule("bot_identity")
    m = _TIME_DATE.match(t)
    if m:
        kind = "time" if "time" in m.group("kind") else "date"
        return Rule("time_date", {"kind": kind})
    m = _MATH.match(t)
    if m and re.search(r"\d", m.group(1)) and re.search(r"[+\-*/%^xX×÷]", m.group(1).strip().lstrip("-")):
        expr = m.group(1).replace("×", "*").replace("÷", "/").replace("^", "**")
        expr = re.sub(r"(?<=[\d)\s])[xX](?=[\d(\s])", "*", expr)
        try:
            value = safe_eval(expr)
            return Rule("math", {"expr": m.group(1).strip(), "value": round(value, 6)})
        except ValueError:
            pass
    found = _extract_math(t)
    if found:
        expr, value = found
        return Rule("math", {"expr": expr, "value": value})
    found = _word_math(t)
    if found:
        expr, value = found
        return Rule("math", {"expr": expr, "value": value})
    m = _FILE_CREATE_NAMED.search(t)
    if m:
        return Rule("file_create", {"file": m.group(1).strip()})
    m = _FOLDER_CREATE.match(t)
    if m:
        name = m.group(1)
        if name:
            return Rule("folder_create", {"folder": name.strip()})
        return Rule("folder_create", {})
    m = _SCREENSHOT.match(t)
    if m:
        return Rule("screenshot")
    rule = parse_web_command(t)
    if rule:
        return rule
    m = _SPECIAL_FOLDER.match(t)
    if m:
        return Rule("special_folder_open", {"folder": m.group(1)})
    m = re.search(r"\bopen\s+([\w][\w\s]*?)[\s?.!]*$", t, re.IGNORECASE)
    if m:
        app = find_app(t)
        if app:
            return Rule("app_open", {"app": app})
    m = _SMALLTALK.match(t)
    if m:
        kind = m.group(1).casefold()
        if kind in ("thanks", "thank you", "thanks a lot", "धन्यवाद", "शुक्रिया", "આભાર"):
            return Rule("smalltalk", {"kind": "thanks"})
        if kind in ("bye", "goodbye", "see you", "अलविदा", "અલવિદા"):
            return Rule("smalltalk", {"kind": "bye"})
        return Rule("smalltalk", {"kind": "how_are_you"})
    name, conf = identity.extract_name(t)
    if name:
        return Rule("set_identity", {"name": name, "conf": conf})
    m = _REF.match(t)
    if m:
        return Rule(_REF_INTENT[m.group(1).lower()], {"reference": True})
    return None


def find_file(text: str) -> str | None:
    """A quoted name (may contain spaces) or the first path-like token with an extension."""
    q = re.search(r"[\"'\u201c\u2018]([^\"'\u201d\u2019]+)[\"'\u201d\u2019]", text)
    if q and "." in q.group(1):
        return q.group(1).strip()
    m = FILE_RE.search(text)
    return m.group(1) if m else None


def find_app(text: str) -> str | None:
    low = text.casefold()
    for alias, target in apps.ALIASES.items():
        if alias in low and len(alias) > 3:
            return target
    names = sorted(apps.allowlist(), key=len, reverse=True) + ["notepad", "calculator", "chrome", "paint", "vs code"]
    for n in names:
        if re.search(rf"(?<!\w){re.escape(n)}(?!\w)", low):
            return n
    return None


_SPECIAL_NAMES = ["recycle bin", "recyclebin", "downloads", "documents", "desktop",
                  "file manager", "file explorer", "explorer"]


def find_special_folder(text: str) -> str | None:
    """Return a known Windows special folder named in the text, else None."""
    low = text.casefold()
    for name in _SPECIAL_NAMES:
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", low):
            return name
    return None


_FOLDER_NAMED = re.compile(r"(?:called|named|कहो|કહો|jiska\s+naam|jiska\s+nam|jenu\s+naam|naam\s+se|naam\s+ka|naam\s+ni)"
                           r"\s+(.+?)(?:\s+(?:ho|hai|rakho|rakhna|che|rakhjo))?[\s?.!]*$", re.IGNORECASE)


def find_folder_name(text: str) -> str | None:
    """Return the folder name after 'called'/'named', else None."""
    m = _FOLDER_NAMED.search(text)
    return m.group(1).strip() if m else None


def extract_file_name(text: str) -> str | None:
    """Filename slot: token after name/named/called, or a token with an extension.

    Filler words (make, one, a, file, text, name, named, called) are never
    taken as the name.
    """
    m = _FILE_CREATE_NAMED.search(text)
    if m:
        return m.group(1).strip()
    f = find_file(text)
    return f


def extract_folder_name(text: str) -> str | None:
    """Folder slot: token after folder...called/named, else None."""
    m = _FOLDER_CREATE.match(text)
    if m:
        name = m.group(1)
        if name:
            return name.strip()
        return None
    return find_folder_name(text)


def _web_url(text: str) -> str | None:
    """Resolve a web_open URL from the user text (delegates to parse_web_command)."""
    rule = parse_web_command(text)
    if rule:
        return rule.slots.get("url")
    return None


def extract_url(text: str) -> str | None:
    """URL slot for web_open (delegates to parse_web_command)."""
    return _web_url(text)


_CONTENT = re.compile(r"(?:with(?: the)? (?:content|text)|saying|that says|:)\s*(.+)$", re.IGNORECASE | re.DOTALL)
_QUOTED = re.compile(r"[\"“]([^\"”]+)[\"”]")


def find_content(text: str) -> str | None:
    q = _QUOTED.search(text)
    if q:
        return q.group(1).strip()
    m = _CONTENT.search(text)
    return m.group(1).strip() if m else None


def office_kind(text: str) -> str:
    low = text.casefold()
    if re.search(r"excel|xlsx|sheet|spreadsheet|एक्सेल|સ્પ્રેડશીટ|એક્સેલ|स्प्रेडशीट", low):
        return "xlsx"
    return "docx"


def find_count(text: str, default: int = 5) -> int:
    m = re.search(r"(\d+)\s*(?:indian\s*)?(?:names?|naam|rows?|पंक्तियों|नाम)", text, re.IGNORECASE)
    return int(m.group(1)) if m else default


def has_pronoun(text: str) -> bool:
    return bool(_PRONOUN.search(text))


# ---------------------------------------------------------------------------
# Command understanding: politeness stripping, synonym and typo tolerant rules.
# Used only after match_rules() found nothing, so earlier behaviour is unchanged.
# ---------------------------------------------------------------------------

_LEAD_NOISE = re.compile(
    r"^(?:(?:hey|hi|hello|ok|okay|yo|oye|arre|are|so|well|listen|suno|sambhdo)[\s,]+)?"
    r"(?:(?:adhyaksh|assistant|jarvis)[\s,]+)?"
    r"(?:(?:please|pls|plz|kindly|zara|jara|can you|could you|would you|will you|can u|i want you to|"
    r"i want to|i need to|i would like to|i'd like to|let's|lets|go ahead and|just|mujhe|mane|"
    r"कृपया|ज़रा|जरा|सुनो|કૃપા કરીને|જરા|સાંભળો)[\s,]+)+", re.IGNORECASE)
_TAIL_NOISE = re.compile(
    r"(?:[\s,]+(?:please|pls|plz|now|jaldi|abhi|atyare|yaar|bhai|dost|for me|right now|thanks|thank you|"
    r"जल्दी|अभी|कृपया|જલ્દી|હમણાં|કૃપા કરીને))+[\s.!?।]*$", re.IGNORECASE)


def clean_command(text: str) -> str:
    """Drop greetings, politeness and filler around a command ('hey assistant, can you open notepad please')."""
    t = " ".join(text.split())
    t = _LEAD_NOISE.sub("", t)
    t = _TAIL_NOISE.sub("", t)
    return t.strip() or text.strip()


def find_app_fuzzy(text: str) -> str | None:
    """Like find_app, but tolerates typos ('notpad', 'calculater', 'crome')."""
    import difflib
    app = find_app(text)
    if app:
        return app
    names = list(apps.allowlist()) + list(apps.ALIASES.values())
    singles = {n: n for n in names if " " not in n}
    for tok in re.findall(r"[a-z]{4,}", text.casefold()):
        close = difflib.get_close_matches(tok, list(singles), n=1, cutoff=0.8)
        if close:
            return singles[close[0]]
    return None


_OPEN_V = (r"(?:open|launch|start|run|fire\s+up|boot\s+up|bring\s+up|khol(?:o|\s+do)?|chalu\s+karo|"
           r"shuru\s+karo|खोलो|चालू\s+करो|शुरू\s+करो|ખોલો|ચાલુ\s+કરો|શરૂ\s+કરો)")
_CLOSE_V = (r"(?:close|quit|exit|kill|terminate|stop|shut\s*down|band\s+karo|bandh\s+karo|"
            r"बंद\s+करो|બંધ\s+કરો)")
_APP_VERB_FIRST = re.compile(rf"^(?P<v>{_OPEN_V}|{_CLOSE_V})\s+(?:the\s+|my\s+)?(?P<rest>.+?)[\s.!?।]*$", re.IGNORECASE)
_APP_VERB_LAST = re.compile(
    r"^(?P<rest>.+?)\s+(?P<v>khol\s+do|kholo|khol|chalu\s+kar(?:o|\s+do)|chalu\s+kari\s+do|start\s+karo|"
    r"band\s+kar(?:o|\s+do)|bandh\s+kar(?:o|\s+do)|bandh\s+kari\s+do|off\s+kar(?:o|\s+do)|"
    r"खोलो|चालू\s+करो|बंद\s+करो|ખોલો|ચાલુ\s+કરો|બંધ\s+કરો)[\s.!?।]*$", re.IGNORECASE)
_SCREENSHOT_X = re.compile(
    r"\b(?:(?:take|capture|grab|snap|get)\s+(?:a\s+|the\s+|my\s+)?(?:screenshot|screen\s*shot|screen\s*capture|screen)|"
    r"screen\s*shot\s+(?:lo|le\s+lo|karo|kari\s+lo|lo\s+ne)|screen\s*capture\s+karo)\b|"
    r"स्क्रीनशॉट\s+(?:लो|लें)|સ્ક્રીનશોટ\s+લો", re.IGNORECASE)
_STATUS_X = re.compile(
    r"\b(?:cpu|ram|disk|storage|processor|battery|system\s+(?:status|health|info)|pc\s+(?:status|health|speed)|"
    r"laptop\s+(?:slow|speed|health)|computer\s+(?:slow|status|health))\b", re.IGNORECASE)
_STATUS_ACT = re.compile(r"\b(?:usage|load|status|free|left|space|check|show|how|kitna|kitni|ketlo|ketli|dikhao|"
                         r"batao|batavo|slow|health|speed|report)\b", re.IGNORECASE)
_TIME_X = re.compile(r"\b(?:what\s+time|time\s+kya|kitne\s+baje|kya\s+baje|ketla\s+vage|ketla\s+vaage|"
                     r"current\s+time|time\s+now)\b|कितने\s+बजे|समय\s+क्या|કેટલા\s+વાગ્યા|સમય\s+શું", re.IGNORECASE)
_DATE_X = re.compile(r"\b(?:what(?:'s|\s+is)\s+(?:the\s+)?(?:date|day)|today'?s\s+date|aaj\s+ki\s+(?:tarikh|date)|"
                     r"aaj\s+kaun\s+sa\s+din|aaj\s+nu\s+(?:tarikh|date)|date\s+kya|tarikh\s+kya)\b|"
                     r"आज\s+की\s+तारीख|આજની\s+તારીખ", re.IGNORECASE)
_REMEMBER_X = re.compile(r"^(?:remember|note\s+down|note|keep\s+in\s+mind|yaad\s+rakh(?:o|na|jo)|याद\s+रखो|યાદ\s+રાખો)"
                         r"\s+(?:that\s+|ki\s+|ke\s+|कि\s+|કે\s+)?(?P<fact>\S.+)$", re.IGNORECASE)
_RECALL_X = re.compile(r"^(?:do\s+you\s+(?:remember|recall)|can\s+you\s+(?:remember|recall)|recall|"
                       r"what\s+did\s+i\s+(?:tell|say|ask)|yaad\s+hai)\b", re.IGNORECASE)
_FILE_VERB = re.compile(
    r"^(?P<v>show|view|display|print|cat|read|open|delete|remove|erase|trash|find|locate|search(?:\s+for)?|"
    r"where\s+is|create|make|new|touch)\s+(?:me\s+)?(?:the\s+|a\s+|an\s+|new\s+)?(?:file\s+|named\s+|called\s+)?(?P<f>\S+?)[\s.!?।]*$",
    re.IGNORECASE)
_FILE_V_INTENT = {"show": "file_read", "view": "file_read", "display": "file_read", "print": "file_read",
                  "cat": "file_read", "read": "file_read", "open": "file_read", "delete": "file_delete",
                  "remove": "file_delete", "erase": "file_delete", "trash": "file_delete",
                  "find": "file_search", "locate": "file_search", "search": "file_search",
                  "search for": "file_search", "where is": "file_search", "create": "file_create",
                  "make": "file_create", "new": "file_create", "touch": "file_create"}


_BARE_CREATE = re.compile(
    r"^(?:create|make|new|banao|bana\s+do)\s+(?:a\s+|an\s+|one\s+|ek\s+)?(?:new\s+|nayi\s+|navi\s+)?(?P<what>file|folder|directory)[\s.!?]*$",
    re.IGNORECASE)


def match_extended(text: str) -> Rule | None:
    """Synonym-, filler- and typo-tolerant rules for apps, files, screenshots, status, time and memory."""
    t = " ".join(text.split())
    m = _BARE_CREATE.match(t)
    if m:  # no name given: the engine asks for it
        return Rule("file_create" if m.group("what").lower() == "file" else "folder_create")
    m = _FILE_VERB.match(t)
    if m and FILE_RE.fullmatch(m.group("f")):
        v = re.sub(r"\s+", " ", m.group("v").casefold())
        return Rule(_FILE_V_INTENT[v], {"file": m.group("f")})
    m = _APP_VERB_FIRST.match(t) or _APP_VERB_LAST.match(t)
    if m and not _has_file_extension(t):
        app = find_app_fuzzy(m.group("rest"))
        if app:
            is_close = re.match(_CLOSE_V, m.group("v"), re.IGNORECASE) or re.search(
                r"band|bandh|off|बंद|બંધ", m.group("v"), re.IGNORECASE)
            return Rule("app_close" if is_close else "app_open", {"app": app})
    if _SCREENSHOT_X.search(t):
        return Rule("screenshot")
    if _STATUS_X.search(t) and _STATUS_ACT.search(t) and not _REMEMBER_X.match(t):
        return Rule("system_status")
    if _RECALL_MORE.match(t) and not _STATUS_X.search(t):
        return Rule("memory_recall")
    if _TIME_X.search(t):
        return Rule("time_date", {"kind": "time"})
    if _DATE_X.search(t):
        return Rule("time_date", {"kind": "date"})
    if _RECALL_X.match(t):
        return Rule("memory_recall")
    if _REMEMBER_X.match(t):
        return Rule("memory_save")
    return _match_more(t)


# --- More generic phrasing: Hindi/Gujarati system words, weekday questions, notes, appends, short greetings ---
_STATUS_INDIC = re.compile(r"सीपीयू|रैम|डिस्क|लैपटॉप|सिस्टम|पीसी|સીપીયુ|રેમ|ડિસ્ક|લેપટોપ|સિસ્ટમ|પીસી|"
                           r"\b(?:drive|hard\s*disk|ssd|hdd)\b", re.IGNORECASE)
_STATUS_INDIC_ACT = re.compile(r"कितन|धीम|खाली|बचा|दिखाओ|बताओ|जांच|जाँच|कैसा|कैसी|કેટલ|ધીમ|ખાલી|બતાવો|કહો|તપાસો|"
                               r"\b(?:kitn\w*|jagah|space|khali|bacha|bachi|baki|ketl\w*|slow|speed|health|check|status|usage)\b",
                               re.IGNORECASE)
_TIME_MORE = re.compile(r"\bwhat(?:'s|s|\s+is)\s+the\s+time\b|\btime\s+(?:pls|please|batao|kaho|bata\s+do)\b|"
                        r"\b(?:ab|abhi)\s+kya\s+baj\w*|\bghadi\b.{0,15}\b(?:time|baj\w*)\b|"
                        r"(?:સમય|ટાઇમ|ટાઈમ)\s*(?:જણાવો|કહો|શું|બતાવો)|(?:समय|टाइम)\s*(?:बताओ|बताइए|क्या)|"
                        r"(?:કેટલા|કેટલાં)\s+વાગ્ય|ketla\s+vag\w+", re.IGNORECASE)
_DAY_MORE = re.compile(r"\b(?:which|what)\s+(?:week)?day\b|\bweekday\b|\bkaun\s*sa\s+(?:din|weekday)\b|"
                       r"\bkons[ao]\s+(?:din|weekday)\b|\bkayo\s+(?:divas|vaar)\b|"
                       r"कौन\s*सा\s+(?:दिन|वार)|કયો\s+દિવસ|ક્યો\s+દિવસ|કયો\s+વાર", re.IGNORECASE)
_RECALL_MORE = re.compile(
    r"^(?:what(?:'s|s|\s+is|\s+was)|tell\s+me|remind\s+me\s+(?:of|what)|wat\s+is)\s+my\s+\w+|"
    r"^(?:mera|meri|mere)\s+\w+(?:\s+\w+){0,2}\s+(?:kya|kaun|kahan|kab|kitne)\b|"
    r"^(?:maro|mari|maru)\s+\w+(?:\s+\w+){0,2}\s+(?:shu|kaun|kya|kyare|kya|kyan)\b|"
    r"^(?:मेरा|मेरी|मेरे)\s+.+(?:क्या|कहाँ|कौन|कब|कितने)|^(?:મારો|મારી|મારું)\s+.+(?:શું|ક્યાં|કઈ|કયો|ક્યારે)",
    re.IGNORECASE)
_NOTE_MORE = re.compile(
    r"^(?:(?:ye|yeh|aa|यह|આ)\s+)?(?:note\s+kar(?:\s+lo|o)?|note\s+kari\s+lo|नोट\s+कर(?:\s+लो|ो)?|નોંધ\s+કરો)"
    r"\s+(?:ki\s+|ke\s+|कि\s+|કે\s+)?\S.+$|"
    r"^(?:bhul(?:na|ta)\s+(?:mat|nahi|nahin)|भूलना\s+मत|ભૂલતા\s+નહીં|ભૂલશો\s+નહીં)\s+\S.+$|"
    r"^(?:please\s+)?(?:don'?t|do\s+not|dont)\s+forget\s+(?:that\s+)?\S.+$", re.IGNORECASE)
_PERCENT = re.compile(r"(\d+(?:\.\d+)?)\s*(?:%|percent|per\s*cent)\s*of\s*(\d+(?:\.\d+)?)", re.IGNORECASE)
_MODULO = re.compile(r"(\d+)\s*(?:mod|modulo|modulus)\s*(\d+)|remainder\s+of\s+(\d+)\s*(?:/|divided\s+by|by)\s*(\d+)",
                     re.IGNORECASE)
_APPEND_EN = re.compile(r"^(?:add|append|write|put|insert|type)\b.{0,60}?\b(?:to|into|in|at\s+the\s+end\s+of)\s+(?P<f>\S+)", re.IGNORECASE)
_APPEND_IN = re.compile(r"^(?P<f>\S+\.[A-Za-z0-9]{1,5})\s+(?:में|mein|me|ma|માં)\s+.+?(?:जोड़ो|जोड़\s*दो|लिखो|लिख\s*दो|\bjod\b|\badd\b|\blikho\b|\blikh\s+do\b|umero|\bumer\w*|\blakho\b|\blakh\w*\s+(?:do|dyo)\b|append|ઉમેરો|લખો)",
                        re.IGNORECASE)
_OFFICE_VERB = re.compile(r"\b(?:create|make|new|generate|prepare)\b|बनाओ|बनाएं|बनाइए|तैयार|બનાવો|તૈયાર|"
                          r"\b(?:banao|bana\s+do|banavo|tayar|taiyar|bani\s+do)\b", re.IGNORECASE)
_SCREEN_MORE = re.compile(r"\bss\s+(?:le|lo|karo|kheench|kheench\s+lo)\b|"
                          r"\b(?:capture|grab|snap|take|save)\b.{0,30}\b(?:display|screen|monitor)\b", re.IGNORECASE)
_GREET_SHORT = re.compile(r"^(?:\S+\s+){0,2}(?:namaste|namaskar|नमस्ते|नमस्कार|નમસ્તે|kem\s+ch+o|કેમ\s+છો)(?:\s+\S+){0,2}[\s.!?]*$",
                          re.IGNORECASE)


def _match_more(t: str) -> Rule | None:
    low = t.casefold()
    pm = _PERCENT.search(t)
    if pm:
        return Rule("math", {"expr": pm.group(0), "value": round(float(pm.group(1)) * float(pm.group(2)) / 100, 6)})
    mm = _MODULO.search(t)
    if mm:
        a, b = (mm.group(1), mm.group(2)) if mm.group(1) else (mm.group(3), mm.group(4))
        if int(b):
            return Rule("math", {"expr": mm.group(0), "value": int(a) % int(b)})
    if _SCREEN_MORE.search(t):
        return Rule("screenshot")
    if _STATUS_INDIC.search(t) and _STATUS_INDIC_ACT.search(t):
        return Rule("system_status")
    if _TIME_MORE.search(t):
        return Rule("time_date", {"kind": "time"})
    if _DAY_MORE.search(t):
        return Rule("time_date", {"kind": "date"})
    m = _APPEND_EN.match(t)
    if m and FILE_RE.fullmatch(m.group("f").strip(".,")):
        return Rule("file_update", {"file": m.group("f").strip(".,")})
    m = _APPEND_IN.match(t)
    if m:
        return Rule("file_update", {"file": m.group("f")})
    fm = FILE_RE.search(t)
    if fm and fm.group(1).lower().rsplit(".", 1)[-1] in ("xlsx", "xls", "docx", "doc") and _OFFICE_VERB.search(t):
        return Rule("office_create")
    if _NOTE_MORE.match(t):
        return Rule("memory_save")
    if _RECALL_MORE.match(t):
        return Rule("memory_recall")
    if len(low.split()) <= 6 and _GREET_SHORT.match(t):
        return Rule("greet")
    return None


# "What is my name" in any phrasing: a question about the stored name, never a declaration of one.
_ID_QUERY = re.compile(
    r"\bwho\s+am\s+i\b|\b(?:what(?:'s|s|\s+is)?|tell\s+me|say|do\s+(?:you|u)\s+(?:know|remember)|"
    r"can\s+(?:you|u)\s+(?:tell|remind)\s+me)\b.{0,25}\b(?:my\s+name(?!\s+is\b)|who\s+i\s+am)\b|"
    r"\b(?:mera|meri)\s+naam\s+(?:yaad|pata|kya|batao|bataiye|bolo|btao)\b|"
    r"\b(?:maru|maaru)\s+naam\s+(?:shu|kaho|yaad|khabar|batavo)\b|"
    r"मेरा\s+नाम.{0,25}(?:क्या|बताओ|बताइए|याद|पता)|"
    r"મારું\s+નામ.{0,25}(?:શું|કહો|યાદ|ખબર|જણાવો)", re.IGNORECASE)
_HELP_X = re.compile(
    r"\b(?:your|tumhare|tumhari|aapke|aapki|tamari|tamara|tamaru|tari|tara)\b.{0,25}"
    r"\b(?:features?|capabilit\w+|suvidha\w*|abilit\w+|functions?|skills?)\b|"
    r"\b(?:what\s+(?:can|do)\s+(?:you|u)\s+(?:do|support|offer)|what\s+are\s+you\s+capable\s+of|"
    r"kya\s+kya\s+kar\s+sakte|shu\s+shu\s+kari\s+shak)\b|"
    r"(?:तुम्हारी|आपकी)\s+(?:\w+\s+)?(?:सुविधा|खूबियां|क्षमता)|(?:તમારી|તારી)\s+(?:\w+\s+)?(?:સુવિધા|ક્ષમતા)",
    re.IGNORECASE)
_SMALL_LEAD = re.compile(r"^(?:(?:ok|okay|alright|fine|cool|so|well|haan|acha|accha|theek hai|thik che)[\s,.]+)+", re.IGNORECASE)
_SMALL_TAIL = re.compile(r"[\s,]+(?:bro|bhai|yaar|dost|mate|buddy|assistant|adhyaksh|sir|ji)[\s.!?]*$", re.IGNORECASE)
_BYE = re.compile(r"^(?:bye+|good\s*bye|good\s*night|see\s+(?:you|ya)(?:\s+(?:later|soon|tomorrow))?|cya|take\s+care|"
                  r"tata|ta\s*ta|alvida|phir\s+milenge|pachi\s+malishu|अलविदा|फिर\s+मिलेंगे|શુભ\s+રાત્રિ|અલવિદા)[\s.!?]*$",
                  re.IGNORECASE)
_THANKS = re.compile(r"^(?:thanks+|thank\s+(?:you|u)(?:\s+(?:so|very)\s+much)?|thx|ty|thanks\s+a\s+lot|shukriya|"
                     r"dhanyavad|dhanyawad|aabhar|abhar|मेहरबानी|शुक्रिया|धन्यवाद|આભાર|ધન્યવાદ)[\s.!?]*$", re.IGNORECASE)


def match_conversational(text: str) -> Rule | None:
    """Identity questions, help requests and goodbyes/thanks, with leading 'ok' and trailing 'bro/yaar' tolerated."""
    t = " ".join(text.split())
    if _ID_QUERY.search(t):
        return Rule("get_identity")
    core = _SMALL_TAIL.sub("", _SMALL_LEAD.sub("", t)).strip() or t
    if _BYE.match(core):
        return Rule("smalltalk", {"kind": "bye"})
    if _THANKS.match(core):
        return Rule("smalltalk", {"kind": "thanks"})
    if _HELP_X.search(t):
        return Rule("help")
    return None


_VERBS = ("open", "close", "launch", "start", "quit", "exit", "kill", "create", "delete", "remove", "search",
          "find", "read", "show", "remember", "screenshot", "append")


def fix_verb_typo(text: str) -> str:
    """Repair a misspelled leading command verb ('clse notepad' -> 'close notepad'); other words are untouched."""
    import difflib
    parts = text.split(None, 1)
    if not parts or len(parts[0]) < 3 or not parts[0].isascii() or parts[0].lower() in _VERBS:
        return text
    close = difflib.get_close_matches(parts[0].lower(), _VERBS, n=1, cutoff=0.78)
    return (close[0] + (" " + parts[1] if len(parts) > 1 else "")) if close else text


def understand(text: str) -> Rule | None:
    """Rules on the raw text, then on the cleaned text, then the extended rules on both."""
    cleaned = clean_command(text)
    for candidate in dict.fromkeys([text.strip(), cleaned, fix_verb_typo(cleaned)]):
        rule = (match_conversational(candidate) or match_features(candidate) or match_rules(candidate)
                or match_extended(candidate))
        if rule:
            return rule
    return None


# ---------------------------------------------------------------------------
# Vision, performance and voice-control commands.
# ---------------------------------------------------------------------------

_TOK = re.compile(r"[a-z]+")


def _has_word_like(t: str, words: tuple[str, ...], cutoff: float = 0.8) -> bool:
    """True if any word of t is (nearly) one of `words`; tolerates typos such as 'stp' for 'stop'."""
    import difflib
    toks = _TOK.findall(t.casefold())
    return any(difflib.get_close_matches(tok, words, n=1, cutoff=cutoff) for tok in toks if len(tok) >= 3)


_V_TARGET = re.compile(
    r"listen|hands?[\s-]*free|\bmic\b|microphone|voice|wake\s*word|\bsunn\w*|sambh\w*|\bsun(?:o|na|ne)\b|"
    r"सुन|हैंड्स|माइक|वेक\s*वर्ड|सांभळ|સાંભળ|હેન્ડ્સ|માઇક|વેક\s*વર્ડ|\bawaaz\b|\bavaj\b|आवाज|અવાજ", re.IGNORECASE)
_V_OFF = re.compile(r"\b(?:stop|end|quit|disable|off|pause|cancel|mute|band|bandh|ruk|ruko)\b|बंद|बन्द|रुको|બંધ|બંધ", re.IGNORECASE)
_V_QUIET = re.compile(r"\b(?:stop\s+(?:talking|speaking)|be\s+quiet|quiet\s+please|shut\s+up|chup|chup\s+raho|chup\s+thai)\b|"
                      r"चुप|ચૂપ|ચુપ", re.IGNORECASE)
_V_SPEAK_OFF = re.compile(
    r"\b(?:stop|turn\s+off|disable|no\s+more|mute|band)\b.{0,20}\b(?:voice\s+repl\w*|repl(?:y|ies)\s+aloud|reading|"
    r"speaking\s+repl\w*|answers?\s+aloud|bolna|bolne|bolvanu|bolvu)\b|"
    r"(?:जवाब|उत्तर)\s+बोलना\s+बंद|બોલવાનું\s+બંધ|\bjaw?ab\s+bolna\s+band\b|\bjavab\s+bolvanu\s+bandh\b|"
    r"\bturn\s+off\s+(?:the\s+)?voice\s+repl\w*", re.IGNORECASE)
_V_SPEAK_ON = re.compile(
    r"\b(?:speak|say|read|tell)\b.{0,30}\b(?:aloud|out\s+loud|repl(?:y|ies)|answers?)\b|"
    r"\b(?:read|say)\s+(?:that|it|this)\s+(?:out\s+loud|aloud)\b|\btalk\s+to\s+me\b|"
    r"\bjaw?ab\b.{0,15}\b(?:bol\s*(?:ke|kar)|bolkar|bolna|sunao|batana)\b|\bjavab\b.{0,15}\b(?:boli?\s*ne|bolvu|sambhdav\w*|kehjo)\b|"
    r"(?:जवाब|उत्तर).{0,12}(?:बोलकर|बोल\s*कर)|જવાબ.{0,12}(?:બોલીને)", re.IGNORECASE)
_V_WAKE = re.compile(r"wake\s*word|वेक\s*वर्ड|વેક\s*વર્ડ", re.IGNORECASE)
_V_ON = re.compile(r"\b(?:start|begin|enable|on|resume|activate|chalu|shuru|keep|always)\b|चालू|शुरू|ચાલુ|શરૂ", re.IGNORECASE)
_V_LANG_CUE = re.compile(r"language|\blang\b|bhasha|भाषा|ભાષા|\bswitch\b|\buse\b|\bin\b", re.IGNORECASE)
_V_LANG_NAME = [(re.compile(r"hindi|हिंदी|हिन्दी|હિન્દી", re.IGNORECASE), "hi-IN"),
                (re.compile(r"gujarati|gujrati|गुजराती|ગુજરાતી", re.IGNORECASE), "gu-IN"),
                (re.compile(r"english|angrezi|अंग्रेज़ी|अंग्रेजी|અંગ્રેજી", re.IGNORECASE), "en-IN")]
_V_SPEECHY = re.compile(r"voice|speech|speak|bol|बोल|બોલ|awaaz|आवाज|અવાજ|talk", re.IGNORECASE)


def voice_action(t: str) -> tuple[str, str] | None:
    """(action, value) for a voice-control phrase, else None."""
    if _V_SPEECHY.search(t) and _V_LANG_CUE.search(t):
        for pat, code in _V_LANG_NAME:
            if pat.search(t):
                return "lang", code
    if _V_QUIET.search(t):
        return "quiet", ""
    if _V_SPEAK_OFF.search(t):
        return "speak_off", ""
    if _V_SPEAK_ON.search(t):
        return "speak_on", ""
    off = bool(_V_OFF.search(t)) or _has_word_like(t, ("stop", "disable", "pause", "quit"), 0.75)
    if _V_WAKE.search(t):
        return ("wake_off" if off else "wake_on"), ""
    if _V_TARGET.search(t) and len(t.split()) <= 8 and not t.rstrip().endswith("?"):
        return ("stop" if off else "start"), ""
    return None


_POWER = re.compile(
    r"\b(?:shut\s*down|shutdown|power\s*off|restart|reboot|log\s*off|log\s*out|sign\s*out|hibernate|put\s+to\s+sleep)\b"
    r".{0,20}\b(?:laptop|computer|pc|system|windows|machine)\b|"
    r"\b(?:laptop|computer|pc|system|windows|machine)\b.{0,12}\b(?:shut\s*down|power\s*off|restart|reboot|hibernate)\b",
    re.IGNORECASE)
_NO_TOOL = re.compile(
    r"^(?:please\s+)?(?:send|write|compose|draft)\s+(?:an?\s+|the\s+|my\s+)?(?:e-?mail|mail|sms|text\s+message|message|whatsapp)\b|"
    r"^(?:please\s+)?(?:call|dial|phone|ring)\s+\w+|^(?:please\s+)?(?:book|order|buy|pay|recharge)\s+\w+",
    re.IGNORECASE)
_VISION_NOUN = re.compile(
    r"\b(?:photos?|images?|pictures?|pics?|webcam|camera|tasveer|tasvir|foto|vision)\b|तस्वीर|फोटो|इमेज|कैमरा|विज़न|विजन|"
    r"ફોટો|ફોટામાં|તસવીર|ઇમેજ|કેમેરા|વિઝન", re.IGNORECASE)
_VISION_CUE = re.compile(
    r"\b(?:what|which|identify|detect|recogni[sz]e|scan|spot|label|name|count|how\s+many|is\s+there|are\s+there|see|sees|"
    r"analy[sz]e|kya|kaun|kaun\s+si|kitn\w+|ketl\w+|shu|kai|dikh\w*|dekhay|batao|kaho|batavo|bata|chalao|chalavo|"
    r"recognition|detection|page|open|kholo)\b|"
    r"क्या|कौन|कितन|बताओ|दिख|चलाओ|खोलो|કઈ|કેટલ|શું|દેખાય|કહો|ચલાવો|ખોલો|છે\s+કે", re.IGNORECASE)
_VISION_DIRECT = re.compile(r"object\s*(?:s\s*)?detect\w*|ऑब्जेक्ट\s*डिटेक्शन|ઓબ્જેક્ટ\s*ડિટેક્શન|image\s*recogni\w+|"
                            r"इमेज\s*रिकग्निशन|ઇમેજ\s*રિકગ્નિશન|\bobjct\s+detecton\b", re.IGNORECASE)
_PAGE_WORDS = re.compile(r"\b(?:open|show|page|kholo|khol|kholi|launch|go\s+to)\b|खोलो|ખોલો|पेज|પેજ", re.IGNORECASE)

_PERF_BOOST = re.compile(
    r"\b(?:boost|speed\s*up|optimi[sz]e|clean\s*up|clean|declutter|free\s+up|release|clear|tune\s+up|faster|fast|"
    r"tez|saaf|safai|junk|temp)\b|तेज़|तेज|साफ|सफाई|ऑप्टिमाइज़|ઝડપી|સાફ|સફાઈ|ઓપ્ટિમાઇઝ", re.IGNORECASE)
_PERF_THING = re.compile(r"\b(?:pc|laptop|computer|system|memory|ram|cpu|temp\s+files?|junk|performance|performence)\b|"
                         r"पीसी|लैपटॉप|कंप्यूटर|कम्प्यूटर|मेमोरी|टेम्प|परफॉर्मेंस|પીસી|લેપટોપ|કમ્પ્યુટર|મેમરી|ટેમ્પ|પરફોર્મન્સ",
                         re.IGNORECASE)
_PERF_HOG = re.compile(
    r"\b(?:which|what|kaun|kaun\s+si|kaun\s+sa|kai|kayo|konsa)\b.{0,25}\b(?:apps?|programs?|processe?s?|process)\b.{0,30}"
    r"\b(?:ram|memory|cpu)\b|\b(?:apps?|programs?|processe?s?)\b.{0,20}\b(?:hogging|eating|using|eats|uses|khata|khati|kha\s+rah\w+|vapre|vaprta)\b|"
    r"\bwhat(?:'s|\s+is)\s+(?:slowing|eating)\b|\b(?:running\s+processes|top\s+processes)\b|"
    r"(?:कौन|कौन\s*सा|कौन\s*सी).{0,25}(?:ऐप|प्रोग्राम|प्रोसेस).{0,25}(?:रैम|मेमोरी|सीपीयू)|"
    r"(?:मेमोरी|रैम).{0,12}(?:खाने|खा\s*रह)|(?:કયો|કઈ).{0,25}(?:એપ|પ્રોગ્રામ|પ્રોસેસ).{0,25}(?:રેમ|મેમરી|સીપીયુ)|"
    r"(?:મેમરી|રેમ).{0,12}ખાતા|\bkya\s+cheez\b.{0,20}\bslow\b|\bshu\s+cheez\b.{0,20}\bslow\b|"
    r"कौन\s*सी\s+चीज़|કઈ\s+વસ્તુ", re.IGNORECASE)
_PERF_PAGE = re.compile(r"(?:performance|performence|परफॉर्मेंस|પરફોર્મન્સ)\s*(?:page|dashboard|पेज|डैशबोर्ड|ડેશબોર્ડ|પેજ)?|"
                        r"\bpc\s+performance\b", re.IGNORECASE)
_PERF_LAG = re.compile(r"\b(?:lag\w*|hang\w*|freez\w*|sluggish)\b|हैंग|हेंग|હેંગ", re.IGNORECASE)


def match_features(text: str) -> Rule | None:
    """Voice control, object detection and PC performance requests."""
    t = " ".join(text.split())
    if (_POWER.search(t) or _NO_TOOL.search(t)) and not _has_file_extension(t):
        return Rule("out_of_scope")  # no tool exists for this: say so instead of guessing an app
    va = voice_action(t)
    if va and not _has_file_extension(t):
        return Rule("voice_control", {"action": va[0], "value": va[1]})
    if _VISION_DIRECT.search(t) or (_VISION_NOUN.search(t) and _VISION_CUE.search(t)):
        if not re.search(r"screen|screenshot|screen\s*shot|स्क्रीन|સ્ક્રીન", t, re.IGNORECASE):
            return Rule("vision_detect", {"open": bool(_PAGE_WORDS.search(t))})
    if _PERF_HOG.search(t):
        return Rule("pc_performance", {"kind": "hogs"})
    if _PERF_PAGE.search(t) and _PAGE_WORDS.search(t):
        return Rule("pc_performance", {"kind": "page"})
    if _PERF_BOOST.search(t) and _PERF_THING.search(t) and not _STATUS_ACT_STRICT.search(t):
        return Rule("pc_performance", {"kind": "boost"})
    if _PERF_LAG.search(t) and _PERF_THING.search(t):
        return Rule("pc_performance", {"kind": "hogs"})
    if re.search(r"\b(?:kill|end|stop|terminate)\b.{0,15}\b(?:heaviest|biggest|top|worst)\b.{0,15}\bprocess", t, re.IGNORECASE):
        return Rule("pc_performance", {"kind": "kill"})
    if _PERF_PAGE.fullmatch(t.strip(" .!?")) or re.fullmatch(r"(?:performence|performance)\s+boost", t.strip(" .!?"), re.IGNORECASE):
        return Rule("pc_performance", {"kind": "boost"})
    return None


# "how much ... free / usage / check": reading numbers is system_status, not a boost request.
_STATUS_ACT_STRICT = re.compile(r"\b(?:how\s+much|how\s+is|usage|status|kitna|kitni|ketlo|ketli|ketlu)\b|कितना|कितनी|કેટલો|કેટલી",
                                re.IGNORECASE)

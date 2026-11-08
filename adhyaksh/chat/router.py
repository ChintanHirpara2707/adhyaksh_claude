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
_LEADING_FILLERS = ("please", "can you", "chrome mein", "in chrome")

# Trailing request verbs removed only at the END of the text (longest first).
_TRAILING_VERBS = (
    "khar do", "kholo ne", "khol do", "kholo",
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
        site = _strip_trailing_verbs(m.group("rest"))
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
        r"(?P<site>.+?)\s+(?:khar do|khol do|kholo ne|kholo|ખોલો ને|ખોલો)"
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


_FOLDER_NAMED = re.compile(r"(?:called|named|कहो|કહો)\s+(.+?)[\s?.!]*$", re.IGNORECASE)


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

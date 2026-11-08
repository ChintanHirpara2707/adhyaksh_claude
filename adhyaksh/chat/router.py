"""Rule layer (greetings, safe math, identity, simple references) and slot extraction."""
from __future__ import annotations

import ast
import operator
import re
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
_WEB_OPEN = re.compile(
    r"^(?:open\s+new\s+tab|open\s+(?P<site>[\w.]+(?:\s+[\w.]+)?)\s+in\s+a\s+new\s+tab|open\s+youtube|"
    r"search\s+google\s+for\s+(?P<query>.+)|in\s+chrome\s+open\s+new\s+tab)[\s?.!]*$",
    re.IGNORECASE)
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
    m = re.search(r"\bopen\s+([\w][\w\s]*?)[\s?.!]*$", t, re.IGNORECASE)
    if m:
        app = find_app(t)
        if app:
            return Rule("app_open", {"app": app})
    m = _SPECIAL_FOLDER.match(t)
    if m:
        return Rule("special_folder_open", {"folder": m.group(1)})
    m = _WEB_OPEN.match(t)
    if m:
        return Rule("web_open", {"url": _web_url(t)})
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
    """Resolve a web_open URL from the user text."""
    m = _WEB_OPEN.match(text)
    if not m:
        return None
    low = text.casefold()
    if m.group("site"):
        site = m.group("site").strip().replace(" ", ".")
        return site if "." in site else site + ".com"
    if "youtube" in low:
        return "youtube.com"
    if "new tab" in low:
        return "about:newtab"
    if m.group("query"):
        return "https://www.google.com/search?q=" + m.group("query").strip()
    return "about:newtab"


def extract_url(text: str) -> str | None:
    """URL slot for web_open."""
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

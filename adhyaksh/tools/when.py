"""Understand reminder times in five language styles: "at 6 pm", "in 20 minutes", "tomorrow 9 am", "every day at 8 pm",
"kal subah 7 baje", "10 minute baad", "शाम 5 बजे", "સાંજે 6 વાગ્યે", "5 vage".

parse() returns the due time (local, naive datetime), whether it repeats daily, and the text with the time words removed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

_UNIT = {"second": 1, "seconds": 1, "sec": 1, "secs": 1, "minute": 60, "minutes": 60, "min": 60, "mins": 60, "minat": 60,
         "hour": 3600, "hours": 3600, "hr": 3600, "hrs": 3600, "ghanta": 3600, "ghante": 3600, "ghante": 3600, "kalak": 3600,
         "मिनट": 60, "मिनिट": 60, "घंटा": 3600, "घंटे": 3600, "सेकंड": 1, "મિનિટ": 60, "કલાક": 3600, "સેકન્ડ": 1}
_REL = re.compile(r"\b(?:in|after)\s+(?P<n>\d+|a|an|one)\s+(?P<u>seconds?|secs?|minutes?|mins?|hours?|hrs?)\b|"
                  r"(?P<n2>\d+)\s*(?P<u2>seconds?|secs?|minutes?|minat|mins?|hours?|hrs?|ghant[ae]|kalak|मिनट|मिनिट|घंटा|घंटे|सेकंड|મિનિટ|કલાક|સેકન્ડ)"
                  r"\s*(?:baad|bad|me|mein|ma|pachi|after|later|बाद|में|પછી|બાદ|માં)", re.IGNORECASE)
_DAY = [(re.compile(r"\bday\s+after\s+tomorrow\b|\bparso\b|\bparson\b|परसों|પરમ\s*દિવસે|\bparam\s*divase\b", re.IGNORECASE), 2),
        (re.compile(r"\btomorrow\b|\btmrw\b|\bkal\b|\bkale\b|\baavti\s*kale\b|कल|આવતીકાલે|કાલે", re.IGNORECASE), 1),
        (re.compile(r"\btoday\b|\baaj\b|\baaje\b|\btonight\b|आज|આજે", re.IGNORECASE), 0)]
_DAILY = re.compile(r"\b(?:every\s*day|everyday|daily|each\s+day|every\s+(?:morning|evening|night)|roz|rozana|har\s+roz|har\s+din|roj|dar\s*roj)\b|"
                    r"रोज़|रोज|हर\s+दिन|प्रतिदिन|દરરોજ|રોજ", re.IGNORECASE)
_PART = [(re.compile(r"\bmorning\b|\bsubah\b|\bsavare\b|\bsavar\b|सुबह|સવારે|સવાર", re.IGNORECASE), "am"),
         (re.compile(r"\bafternoon\b|\bdopahar\b|\bbapore\b|दोपहर|બપોરે", re.IGNORECASE), "noon"),
         (re.compile(r"\bevening\b|\bshaam\b|\bsham\b|\bsanje\b|\bsaanje\b|शाम|સાંજે|સાંજ", re.IGNORECASE), "pm"),
         (re.compile(r"\bnight\b|\btonight\b|\braat\b|\brate\b|\braatre\b|रात|રાત્રે|રાત", re.IGNORECASE), "night")]
_CLOCK = re.compile(r"(?:\bat\s+|\b@\s*)?(?P<h>\d{1,2})(?:[:.](?P<m>\d{2}))?\s*(?P<ap>a\.?m\.?|p\.?m\.?)(?![a-z])|"
                    r"(?:\bat\s+)(?P<h2>\d{1,2})(?:[:.](?P<m2>\d{2}))?\b(?!\s*(?:minutes?|mins?|hours?|%))|"
                    r"\b(?P<h3>\d{1,2})(?:[:.](?P<m3>\d{2}))?\s*(?:baje|bje|baja|vage|vagye|vagya|vaage|o'?\s*clock|बजे|बजकर|વાગ્યે|વાગે|વાગ્યા)|"
                    r"\b(?P<h4>\d{1,2})[:.](?P<m4>\d{2})\b|"
                    r"\b(?P<h5>\d{1,2})\s+(?:in\s+the\s+morning|in\s+the\s+evening|at\s+night)\b", re.IGNORECASE)
_WAKE = re.compile(r"\bwake\s+me\b|\balarm\b|\buthana\b|\buthado\b|उठा|જગાડ|એલાર્મ|अलार्म", re.IGNORECASE)


@dataclass
class When:
    due: datetime | None
    repeat: str  # "none" or "daily"
    rest: str
    found: bool


def _clean(text: str, spans: list[tuple[int, int]]) -> str:
    out, last = [], 0
    for a, b in sorted(spans):
        if a >= last:
            out.append(text[last:a])
            last = b
    out.append(text[last:])
    return " ".join("".join(out).split())


def parse(text: str, now: datetime | None = None) -> When:
    now = (now or datetime.now()).replace(second=0, microsecond=0)
    t = text or ""
    spans: list[tuple[int, int]] = []
    repeat = "none"
    m = _DAILY.search(t)
    if m:
        repeat = "daily"
        spans.append(m.span())
    r = _REL.search(t)
    if r:
        n = r.group("n") or r.group("n2")
        n = 1 if str(n).lower() in ("a", "an", "one") else int(n)
        unit = (r.group("u") or r.group("u2") or "").lower()
        secs = _UNIT.get(unit, _UNIT.get(unit.rstrip("s"), 60))
        spans.append(r.span())
        return When(now + timedelta(seconds=n * secs), repeat, _clean(t, spans), True)
    day_offset = None
    for pat, off in _DAY:
        dm = pat.search(t)
        if dm:
            day_offset = off
            spans.append(dm.span())
            break
    part = None
    for pat, name in _PART:
        pm = pat.search(t)
        if pm:
            part = name
            spans.append(pm.span())
            break
    c = _CLOCK.search(t)
    hour = minute = None
    ap = None
    if c:
        spans.append(c.span())
        for hk, mk in (("h", "m"), ("h2", "m2"), ("h3", "m3"), ("h4", "m4"), ("h5", None)):
            if c.group(hk):
                hour = int(c.group(hk))
                minute = int(c.group(mk)) if mk and c.group(mk) else 0
                break
        if c.group("ap"):
            ap = "pm" if c.group("ap").lower().startswith("p") else "am"
        elif c.group("h5"):
            ap = "am" if "morning" in c.group(0).lower() else "pm"
        if hour is None or hour > 23 or minute > 59:
            hour = None
    if hour is None and day_offset is None and part is None:
        return When(None, repeat, _clean(t, spans), repeat != "none")
    if hour is None:  # a day or day part without a clock time
        hour, minute = {"am": 9, "noon": 14, "pm": 18, "night": 21, None: 9}[part], 0
    elif ap is None and hour <= 12:
        if part == "am":
            ap = "am"
        elif part in ("pm", "noon"):
            ap = "pm"
        elif part == "night":
            ap = "am" if hour <= 4 else "pm"
        elif _WAKE.search(t):
            ap = "am"
    if ap == "pm" and hour < 12:
        hour += 12
    elif ap == "am" and hour == 12:
        hour = 0
    base = now + timedelta(days=day_offset or 0)
    due = base.replace(hour=hour, minute=minute)
    if day_offset is None and ap is None and hour < 12 and due <= now:
        due = due + timedelta(hours=12)  # "at 6" in the afternoon means 6 pm
    if day_offset is None and due <= now:
        due = due + timedelta(days=1)
    return When(due, repeat, _clean(t, spans), True)


_COMMAND = re.compile(
    r"\b(?:please|pls|kindly|can\s+you|could\s+you|set\s+(?:a|an|the|my)?\s*(?:reminder|alarm)|add\s+(?:a\s+)?reminder|create\s+(?:a\s+)?reminder|"
    r"remind\s+me(?:\s+(?:to|about|that|of))?|reminder(?:\s+(?:to|for|about))?|wake\s+me\s+up|alarm|for|at|on|to|"
    r"mujhe|mane|yaad\s+dila(?:na|o|ye|iye|jo)?|yaad\s+apav(?:jo|o|e)?|ki|ke|ka\s+reminder|nu\s+reminder|reminder\s+laga\w*|laga\s+do|"
    r"set\s+kar\w*|mukjo|muki\s+do|alarm\s+laga\w*)\b|"
    r"मुझे|की\s+याद\s+दिलाना|याद\s+दिलाना|याद\s+दिला(?:ओ|ना|एं|इए)?|का\s+अलार्म|अलार्म|लगा\s+दो|रिमाइंडर|"
    r"મને|યાદ\s+અપાવજો|યાદ\s+અપાવ(?:ો|જો)?|નું\s+રિમાઇન્ડર|રિમાઇન્ડર|એલાર્મ|મૂકી\s+દો", re.IGNORECASE)


def reminder_text(text: str, wake: bool = False) -> str:
    """What to remind about: the request without time words and command words."""
    rest = parse(text).rest
    core = _COMMAND.sub(" ", rest)
    core = re.sub(r"\b(?:nu|no|ni|ka|ki|ke|to|that)\s*$", "", " ".join(core.split()), flags=re.IGNORECASE).strip(" ,.:-")
    core = re.sub(r"^(?:nu|no|ni|ka|ki|ke|to|that|about)\b\s*", "", core, flags=re.IGNORECASE).strip(" ,.:-")
    if not core:
        return "Wake up" if (wake or _WAKE.search(text)) else "Reminder"
    return core[:200]


def describe(due: datetime, repeat: str = "none", now: datetime | None = None) -> str:
    now = now or datetime.now()
    clock = due.strftime("%I:%M %p").lstrip("0")
    if repeat == "daily":
        return f"every day at {clock}"
    if due.date() == now.date():
        return f"today at {clock}"
    if due.date() == (now + timedelta(days=1)).date():
        return f"tomorrow at {clock}"
    return due.strftime("%A %d %B at ") + clock

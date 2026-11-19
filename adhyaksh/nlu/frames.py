"""Frame parser: a command as ACTION + NEGATION + TARGET, decided separately.

    "zara spotify band mat karo"  ->  Frame(action="close", negated=True, target_type="app", target="spotify")

* The action comes from the shared verb lexicon (nlu/lexicon.py); opposite actions are different values of one
  slot, so "open" and "close" can never be confused by sharing an object.
* Negation is detected in all five language styles. A negated command is never executed.
* The target comes from nlu/entities.py and is always a clean canonical value.
* :data:`INTENTS` maps (action, target type) to an intent. A frame only becomes a command when that pair exists
  and nothing is ambiguous (two different actions, two targets); otherwise the caller falls back to the other
  rules, the classifier or the language model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache

from adhyaksh.nlu import entities, lexicon

INTENTS: dict[tuple[str, str], str] = {
    ("open", "app"): "app_open", ("close", "app"): "app_close",
    ("create", "file"): "file_create", ("delete", "file"): "file_delete",
    ("search", "file"): "file_search",
}
# System targets: the action becomes an operation slot of one intent per target.
VOLUME_OPS = {"increase": "up", "decrease": "down", "set": "set", "mute": "mute", "unmute": "unmute",
              "close": "mute", "open": "unmute"}  # "volume band karo" mutes, "awaaz chalu karo" unmutes
BRIGHTNESS_OPS = {"increase": "up", "decrease": "down", "set": "set"}
for _a in VOLUME_OPS:
    INTENTS[(_a, "volume")] = INTENTS[(_a, "mic")] = "volume_control"
for _a in BRIGHTNESS_OPS:
    INTENTS[(_a, "brightness")] = "brightness_control"
_LEVEL_TARGETS = ("volume", "mic", "brightness")
# Words a pure "action + target" command may contain besides the verb and the target. Anything else (content to
# write, a destination folder, a second instruction) means the request carries more than a frame models, and the
# richer rules handle it instead.
_FRAME_WORDS = {"named", "called", "titled", "naam", "ki", "ka", "ke", "ni", "nu", "no", "नाम", "की", "का", "के",
                "નામની", "નામનું", "નામનો", "new", "a", "an", "the", "files", "file", "for", "me", "with", "of",
                # levels: "set volume to 40 percent", "thodi brightness badhao", "laptop ka volume"
                "to", "by", "at", "percent", "pratishat", "takka", "taka", "टका", "प्रतिशत", "ટકા", "level", "thoda", "thodi",
                "thodu", "little", "bit", "more", "less", "zyada", "vadhare", "pe", "par", "per", "screen", "display",
                "laptop", "pc", "computer", "system", "लैपटॉप", "को", "ને", "थोड़ा", "थोड़ी", "થોડું", "થોડો",
                # "again" words do not change a command: "awaaz wapas chalu karo", "ફરી ચાલુ કરો"
                "again", "back", "wapas", "vapas", "phir", "fir", "fari", "pachu", "pacho", "फिर", "वापस", "ફરી", "પાછું"}
# Verbs whose meaning depends on the target: only trusted with an app ("run python" is not an app launch).
_APP_ONLY = {"run", "start", "stop", "end", "kill", "terminate", "load up", "turn on", "turn off", "shut", "chalu",
             "band", "bandh", "चालू", "बंद", "ચાલુ", "બંધ", "on karo", "off karo", "ऑन करो", "ऑफ करो", "ઓન કરો", "ઓફ કરો"}
_B = r"(?<![\wऀ-ॿ઀-૿'])"
_E = r"(?![\wऀ-ॿ઀-૿'])"
# English: a negation that governs the clause ("don't ...", "wait, do not ...", "I don't want to ...").
_EN_NEG_LEAD = re.compile(r"^(?:(?:wait|no|ok|okay|hey|please|actually|stop)[\s,!.]+)*(?:please\s+)?"
                          r"(?:don'?t|do\s+not|never|no\s+need\s+to|i\s+(?:do\s+not|don'?t)\s+want\s+(?:you\s+)?to|"
                          r"there\s+is\s+no\s+need\s+to|you\s+(?:should\s+not|shouldn'?t|must\s+not))\b", re.IGNORECASE)
# Particles that only mean "please" at the very end of a request ("chalu karo na"), not "not".
_EMPHATIC_TAIL = {"na", "ना", "ના"}
# A request led by a different command keeps its own meaning even if it contains a negated verb:
# "remember that I should not open chrome", "remind me not to delete it", "write 'do not open' in notes.txt".
_OTHER_COMMAND_LEAD = re.compile(
    r"^(?:(?:hey|ok|okay|please|assistant|adhyaksh)[\s,]+)*(?:(?:don'?t|do\s+not|never)\s+forget|"  # = remember
    r"remember|note|remind|write|type|copy|save|tell|say|"
    r"translate|explain|summari[sz]e|yaad|likh|likho|lakho|bol|batao|kaho|याद|लिख|बताओ|યાદ|લખ|કહો)\b", re.IGNORECASE)
# Real questions ("why is chrome not opening?"), not polite requests ("can you not open chrome").
_QUESTION = re.compile(r"\?\s*$|^(?:why|how|what|when|where|which|is|are|was|does|did|kya|kyu|kyon|kem|shu|કેમ|ક્યાં|क्यों|क्या)\b",
                       re.IGNORECASE)


@dataclass
class Frame:
    action: str | None = None
    negated: bool = False
    target_type: str | None = None
    target: str | None = None
    actions_seen: list[str] = field(default_factory=list)
    verb: str = ""

    @property
    def intent(self) -> str | None:
        if self.action and self.target_type and not self.ambiguous:
            return INTENTS.get((self.action, self.target_type))
        return None

    @property
    def ambiguous(self) -> bool:
        return len(set(self.actions_seen)) > 1

    @property
    def complete(self) -> bool:
        return self.intent is not None and bool(self.target)

    level: int | None = None

    def slots(self) -> dict:
        if self.target_type in ("volume", "mic"):
            return {"device": "mic" if self.target_type == "mic" else "speaker", "op": VOLUME_OPS.get(self.action or ""),
                    "level": self.level}
        if self.target_type == "brightness":
            return {"op": BRIGHTNESS_OPS.get(self.action or ""), "level": self.level}
        key = {"app": "app", "file": "file"}.get(self.target_type or "", "target")
        return {key: self.target} if self.target else {}


@lru_cache(maxsize=1)
def _neg_alternation() -> str:
    words = sorted({w for lang, ws in lexicon.NEGATION.items() if lang != "en" for w in ws}, key=len, reverse=True)
    return "(?:" + "|".join(re.escape(w) for w in words) + ")"


@lru_cache(maxsize=1)
def _verb_patterns() -> list[tuple[re.Pattern, str, str]]:
    """(pattern, action, verb form) for every verb form, longest first. A negation particle may sit between the
    parts of a multi-word verb ("band mat karo", "kadhi na nakho", "બંધ ના કરો"), so the verb is still found."""
    forms = [(v, action) for action, by_lang in lexicon.ACTIONS.items() for verbs in by_lang.values() for v in verbs]
    forms = sorted(set(forms), key=lambda fa: len(fa[0]), reverse=True)
    gap = r"\s+(?:" + _neg_alternation() + r"\s+)?"
    return [(re.compile(_B + gap.join(re.escape(part) for part in v.split()) + _E, re.IGNORECASE), a, v) for v, a in forms]


@lru_cache(maxsize=1)
def _neg_words() -> re.Pattern:
    return re.compile(_B + _neg_alternation() + _E, re.IGNORECASE)


def _find_actions(text: str, target_span: tuple[int, int] | None) -> list[tuple[str, str, int, int]]:
    """Non-overlapping verb matches (action, form, start, end), longest forms first, outside the target's words."""
    taken: list[tuple[int, int]] = [target_span] if target_span else []
    found = []
    for pat, action, form in _verb_patterns():
        for m in pat.finditer(text):
            s, e = m.span()
            if any(s < te and ts < e for ts, te in taken):
                continue
            taken.append((s, e))
            found.append((action, form, s, e))
    return sorted(found, key=lambda f: f[2])


def _negated(text: str, verbs: list[tuple[str, str, int, int]]) -> bool:
    low = text.strip()
    if _EN_NEG_LEAD.search(low):
        return True
    if not verbs:
        return False
    first_verb = verbs[0][2]
    # English "not" between a modal and the verb ("can you not open"), or a negation right before the verb.
    if re.search(r"\b(?:not|never|don'?t)\s+(?:\w+\s+){0,2}$", low[:first_verb], re.IGNORECASE):
        return True
    for m in _neg_words().finditer(low):
        word = m.group(0).casefold()
        if word in _EMPHATIC_TAIL and m.start() >= verbs[-1][3]:
            continue  # "chalu karo na", "बंद करो ना क्रोम": after the verb it is emphasis; before or inside it negates
        # A negation particle anywhere around the verb phrase negates it (before: "mat kholo"; inside:
        # "band mat karo", "kadhi na nakho"; after: "kholna nahi"); one far away in another clause does not.
        verb_start, verb_end = verbs[0][2], verbs[-1][3]
        if verb_start - 25 <= m.start() <= verb_end + 25:
            return True
    return False


def _target(text: str) -> tuple[str | None, str | None, tuple[int, int] | None]:
    """(type, canonical value, span in text). A file with an extension wins; then a system target named by a noun
    (volume, mic, brightness); then an app."""
    name = entities.find_file(text)
    if name:
        i = text.find(name)
        return "file", name, (i, i + len(name)) if i >= 0 else None
    system = entities.system_target(text)
    if system:
        return system[0], system[0], system[1]
    app = entities.find_app(text)
    if not app and re.search(r"\bfiles?\b|फाइल|ફાઇલ", text, re.IGNORECASE):
        name = entities.named(text)
        if name:  # "files named invoice": a file name without an extension
            i = text.find(name)
            return "file", name, (i, i + len(name)) if i >= 0 else None
    fuzzy = False
    if not app:
        app = entities.find_app(text, fuzzy=True)
        fuzzy = app is not None
    if app:
        low = text.casefold()
        span = None
        for spelling, key in entities.app_spellings():
            if key == app:
                i = low.find(spelling)
                if i >= 0:
                    span = (i, i + len(spelling))
                    break
        return "app", app, span if not fuzzy else None
    return None, None, None


def parse(text: str) -> Frame:
    """The frame of one request (one step; multi-step text is split before this)."""
    t = " ".join((text or "").split())
    ttype, target, span = _target(t)
    verbs = _find_actions(t, span)
    if ttype is None and verbs and {a for a, *_ in verbs} <= {"mute", "unmute"}:
        ttype = target = "volume"  # a bare "mute" / "unmute" can only mean the speakers
    if ttype not in ("app",) + _LEVEL_TARGETS:
        verbs = [v for v in verbs if v[1] not in _APP_ONLY]
    if ttype in _LEVEL_TARGETS:
        # Only actions that make sense for a level count ("set volume" yes; a "create" or "search" verb is noise).
        verbs = [v for v in verbs if (v[0], ttype) in INTENTS]
    frame = Frame(target_type=ttype, target=target, actions_seen=[a for a, *_ in verbs])
    if verbs:
        frame.action, frame.verb = verbs[0][0], verbs[0][1]
        # "make sure you close it" style: when several verbs agree, keep one; disagreement is ambiguous.
    if ttype in _LEVEL_TARGETS:
        frame.level = entities.number(t)
        if not verbs and frame.level is not None:
            frame.action = "set"  # "volume 40", "brightness 70 percent"
    frame.negated = _negated(t, verbs)
    return frame


def negated_command(text: str) -> Frame | None:
    """The frame of a request the user said NOT to do ("don't open notepad", "chrome band mat karo"),
    else None. Questions ("why is chrome not opening?") are not commands and are left alone."""
    t = " ".join((text or "").split())
    if not t or _QUESTION.search(t) and not _EN_NEG_LEAD.search(t) or _OTHER_COMMAND_LEAD.search(t):
        return None
    frame = parse(t)
    if not frame.negated:
        return None
    if frame.action or _EN_NEG_LEAD.search(t):
        return frame
    return None


# A location that names the default work folder adds nothing (files go there anyway). Any other folder is a real
# destination the frame does not model, so it stays a leftover and the richer rules decide.
_DEFAULT_LOCATION = re.compile(r"\b(?:in|inside|into|under)\s+(?:my\s+|the\s+)?(?:work(?:ing)?\s+folder|workspace|"
                               r"default\s+folder|work\s+directory)\b", re.IGNORECASE)


def _leftover(text: str, frame: Frame) -> list[str]:
    """Words that are neither the verb, the target, a filler, a target noun nor a naming word."""
    t = _DEFAULT_LOCATION.sub(" ", text.casefold())
    if frame.target:
        t = t.replace(frame.target.casefold(), " ")
        for spelling, key in entities.app_spellings():
            if key == frame.target:
                t = re.sub(_B + re.escape(spelling) + _E, " ", t)
    for pat, _action, _form in _verb_patterns():
        t = pat.sub(" ", t)
    allowed = entities._command_words() | _FRAME_WORDS
    if frame.target_type in _LEVEL_TARGETS:
        t = re.sub(r"[\d०-९૦-૯]+", " ", t)  # the level number is a slot, not a leftover
    return [w for w in re.findall(r"[\wऀ-ॿ઀-૿']+", t) if w not in allowed]


def command(text: str) -> Frame | None:
    """A complete, unambiguous, non-negated command frame with nothing else in the request, else None."""
    t = " ".join((text or "").split()).strip(" .!?।")
    frame = parse(t)
    if frame.negated or not frame.complete or _leftover(t, frame):
        return None
    return frame

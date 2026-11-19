"""Chat engine: message in, reply out. Rules, then the trained model, then tools via safety."""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime
from pathlib import Path

from adhyaksh import config, logging_setup, responses
from adhyaksh.chat import context, identity, router
from adhyaksh.agent import native as agent_native
from adhyaksh.llm import base as llm
from adhyaksh.memory import store
from adhyaksh.nlu import entities, factorized, frames, registry
from adhyaksh.rag import answerer, sources
from adhyaksh.result import (E_BLOCKED, E_LOW_CONFIDENCE, E_NEEDS_CONFIRM, E_NO_API_KEY, Result)
from adhyaksh.safety import policy
from adhyaksh.tools import apps, audio, clipboard, display, features, files, office, processes, reminders, system
from adhyaksh.voice import speech

MAX_MESSAGE = 8000  # long notes and pasted text can be saved to memory
OS_INTENTS = {
    "file_create", "file_read", "file_update", "file_delete", "file_search",
    "folder_create", "office_create", "app_open", "app_close",
    "special_folder_open", "web_open", "screenshot", "system_status", "pc_performance",
    "process_list", "process_kill", "clipboard_read", "clipboard_write",
    "volume_control", "brightness_control",
}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp"}
YES = {"yes", "y", "confirm", "yes please", "haan", "ha", "हाँ", "हां", "હા", "ok confirm"}
NO = {"no", "n", "cancel", "nahi", "nahin", "na", "नहीं", "ના", "નહીં", "nope"}
EXAMPLE_NAME = "names.xlsx"


def detect_lang(text: str) -> str:
    if re.search(r"[\u0900-\u097F]", text):
        return "hi"
    if re.search(r"[\u0A80-\u0AFF]", text):
        return "gu"
    return "en"


def _t(key: str, lang: str, **kw) -> str:
    return responses.t(key, lang, **kw)


def _ctx_for(text: str, intent: str, token: str | None = None) -> dict:
    return {"user_text": text, "intent": intent, "token": token}


_EN_QW = {"what","who","where","when","why","how","which","whose","whom","can","could","would","should",
          "do","does","did","is","are","was","were","will","am","may","might","shall","tell","show",
          "please","give","i want","i want to","define","definition"}
_HI_QW = {"क्या","कौन","कहाँ","कैसे","क्यों","किस","कौनसा","कितना","कितनी",
          "kya","kaun","kahan","kaise","kyun","kis","kitna","kitni","kab","kya hai",
          "kaun hai","kahan hai","kitna hai","kya che","kaun che","kitna che"}
_GU_QW = {"શું","કોણ","ક્યાં","કેવી","કેમ","શું","કયો","કયા","કેટલું","કેટલી",
          "shu","kon","kyare","kevi","kem","shu che","kon che","kitlo che","kitli che",
          "kya che","kaun che","shu thay che"}
_DATE_WORDS = re.compile(r"\b(?:date|today|tarikh|tareekh|day|weekday|din|vaar|divas)\b|तारीख|તારીખ|डेट|ડેટ|दिन|दिनांक|દિવસ|વાર",
                         re.IGNORECASE)


def _time_date_kind(text: str) -> str:
    return "date" if _DATE_WORDS.search(text) else "time"


def _is_question(text: str) -> bool:
    """Heuristic: true for requests/questions, false for plain statements like 'Current time is 10:15 AM'."""
    t = text.strip()
    if not t:
        return False
    if "?" in t:
        return True
    low = t.casefold()
    words = low.split()
    if words and words[0] in _EN_QW:
        return True
    for marker in _HI_QW | _GU_QW:
        if marker in low:
            return True
    return False


def _looks_multi_step(text: str) -> bool:
    """Heuristic: true when the request bundles several actions (e.g. 'create x and open it')."""
    low = text.casefold()
    if not re.search(r"\b( and | then | aur | ke baad | , )\b", low):
        return False
    verbs = ["create", "make", "read", "open", "delete", "remove", "search", "find",
             "remember", "save", "take", "screenshot", "show", "status", "close",
             "लिखो", "खोलो", "ढूंढो", "याद", "स्क्रीनशॉट", "बनाओ"]
    return sum(1 for v in verbs if v in low) >= 2


_FOLDER_WORD = re.compile(r"\b(folder|directory|dir)\b(?!\.\w)", re.IGNORECASE)


# Replies that drop a pending clarifying question ("no" may be a real answer, so it is not one of them).
_DROP_REQUEST = {"cancel", "stop", "never mind", "nevermind", "forget it", "leave it", "rehne do", "rahne do", "jane do",
                 "javado", "jaava do", "kuch nahi", "रहने दो", "छोड़ो", "રહેવા દો", "જવા દો"}

_NEG_VERB = {"open": "open", "close": "close", "create": "create", "delete": "delete", "search": "search for"}


def _negated_reply(frame, lang: str) -> _Reply:
    """Acknowledge a request the user said not to carry out. Nothing is run."""
    if frame.action and frame.target:
        what = f"{_NEG_VERB.get(frame.action, frame.action)} {frame.target}"
        return _Reply(_t("negated", lang, what=what, target=frame.target), "negated", 1.0, action="negated")
    return _Reply(_t("negated_plain", lang), "negated", 1.0, action="negated")


def _correct_file_folder(intent: str, slots: dict, text: str) -> tuple[str, dict]:
    """Decide file vs folder from folder-words in the text before trusting the intent. An explicit file name with
    an extension ("create groceries.txt in my work folder") is always a file; the folder word is its location."""
    slots = dict(slots)
    if _FOLDER_WORD.search(text) and not entities.find_file(text):
        if intent == "file_create":
            intent = "folder_create"
            if "file" in slots and not slots.get("folder"):
                slots["folder"] = slots.pop("file")
    return intent, slots


COWORK_INTENTS = {"process_list", "process_kill", "reminder_set", "reminder_list", "reminder_cancel", "clipboard_read",
                  "clipboard_write"}


def _model_slots(intent: str, text: str) -> dict:
    if intent in COWORK_INTENTS:
        r = router.match_cowork(text)
        return dict(r.slots) if r and r.intent == intent else {}
    """Extract slots for a model-predicted intent, using the same extractors
    as the rule layer (filename, folder name, URL, app). Verbs and filler
    words are never taken as the name."""
    if intent in ("file_create", "file_read", "file_update", "file_delete", "file_search"):
        f = router.extract_file_name(text)
        return {"file": f} if f else {}
    if intent == "folder_create":
        f = router.extract_folder_name(text)
        return {"folder": f} if f else {}
    if intent == "web_open":
        u = router.extract_url(text)
        return {"url": u} if u else {}
    if intent in ("app_open", "app_close"):
        a = router.find_app(text)
        return {"app": a} if a else {}
    if intent == "special_folder_open":
        fo = router.find_special_folder(text)
        return {"folder": fo} if fo else {}
    if intent == "time_date":
        return {"kind": _time_date_kind(text)}
    if intent == "vision_detect":
        return {"open": bool(router._PAGE_WORDS.search(text))}
    if intent == "pc_performance":
        r = router.match_features(text)
        if r and r.intent == "pc_performance":
            return r.slots
        return {"kind": "page" if router._PAGE_WORDS.search(text) and router._PERF_PAGE.search(text) else "hogs"}
    if intent == "voice_control":
        va = router.voice_action(text)
        return {"action": va[0], "value": va[1]} if va else {}
    if intent == "set_identity":
        name, conf = identity.extract_name(text)
        return {"name": name, "conf": conf} if name else {}
    return {}


def _agent_dispatch(text: str, ctx: context.Context, convo_id: int, lang: str, mode: str = "cowork") -> _Reply:
    """Run the tool-calling agent for a request the offline path could not place."""
    res = agent_native.run(text, convo_id, lang, mode)
    if res.get("disabled"):
        return _Reply(res.get("reason", "Agent unavailable."), "unknown", 0.0)
    if res.get("failed"):
        return _Reply(_cannot_do_yet(lang), "unknown", 0.0, action="low_confidence")
    return _native_reply(res, ctx, text)


def _native_reply(res: dict, ctx: context.Context, text: str) -> _Reply:
    """Turn a native agent result into a reply (final answer, or a pending confirmation)."""
    confirmation = res.get("confirmation")
    if res.get("ask"):
        ctx.pending_agent_ask = {"token": res["ask"]["token"], "text": text}
        ctx.agent_steps = res.get("steps", [])
        return _Reply(res.get("reply") or res["ask"]["question"], "agent_ask", 1.0, action="clarify",
                      extra={**(res.get("ui") or {}), "options": res["ask"].get("options") or []})
    if confirmation:
        ctx.pending_agent_confirm = {"token": confirmation["token"], "action": confirmation["action"],
                                     "target": confirmation["target"], "text": text, "native": True}
        return _Reply(f"Confirm {confirmation['action'].replace('_', ' ')} on {confirmation['target']}? Say yes to confirm or no to cancel.",
                      "agent_confirm", action="agent_confirm", confirmation=confirmation, extra=res.get("ui") or {})
    ctx.agent_steps = res.get("steps", [])
    return _Reply(res.get("reply") or "I could not complete that.", "agent", 1.0, action="agent", extra=res.get("ui") or {})


def _native_dispatch(text: str, ctx: context.Context, convo_id: int, lang: str, mode: str) -> _Reply | None:
    """Tool-calling agent first. None means the model is unavailable or unreachable: use the offline path."""
    res = agent_native.run(text, convo_id, lang, mode)
    if res.get("disabled") or res.get("failed"):
        return None
    return _native_reply(res, ctx, text)


def _context_answer(text: str, ctx: context.Context, lang: str) -> _Reply | None:
    """Answer a question from the user's own memory or attached documents before guessing an intent."""
    if not (_is_question(text) or _GENERAL_CUES.search(text)):
        return None
    hit = store.best_match(text)
    if hit:
        return _Reply(_t("memory_recall", lang, answer=hit["answer"]), "memory_recall", action="memory")
    if sources.count() > 0:  # the active notebook has sources: answer from them when they match
        res = answerer.answer(text)
        if res.data.get("found"):
            return _Reply(res.data["answer"], "doc_question", action="doc_answer", sources=res.data["sources"])
    return None


def _finish_agent_confirmation(ctx: context.Context, accept: bool,
                               convo_id: int, lang: str) -> _Reply:
    p, ctx.pending_agent_confirm = ctx.pending_agent_confirm, None
    if p.get("native"):
        if not accept:
            policy.cancel_guarded(p["token"])
            agent_native.cancel(p["token"])
            return _Reply(_t("cancelled", lang), "agent_confirm", action="cancel")
        return _native_reply(agent_native.resume(p["token"]), ctx, p["text"])
    # Confirmations always come from the tool-calling agent now; an old pending entry is simply cancelled.
    policy.cancel_guarded(p["token"])
    return _Reply(_t("cancelled", lang), "agent_confirm", action="cancel")


def _error_reply(res: Result, lang: str) -> str:
    return _t("error", lang, reason=res.message.rstrip(".") or "unknown error")


_CAPABILITIES = ("I can create, read, update, delete and search files; create Excel and Word files; "
                 "open and close allowed applications; take screenshots; check system status; "
                 "remember facts; and answer questions from your documents or the web.")


def _cannot_do_yet(lang: str) -> str:
    return _t("cannot_do_yet", lang, capabilities=_CAPABILITIES)


class _Reply:
    def __init__(self, text: str, intent: str, conf: float = 1.0, action: str = "", confirmation: dict | None = None,
                 sources: list | None = None, suggest_mode: str | None = None, extra: dict | None = None):
        self.extra = extra or {}  # UI hints: open_page, voice_cmd
        self.text, self.intent, self.conf, self.action = text, intent, conf, action
        self.confirmation, self.sources, self.suggest_mode = confirmation, sources or [], suggest_mode


def _confirm_reply(res: Result, lang: str, ctx: context.Context, retry, intent: str, shown: str) -> _Reply:
    d = res.data
    ctx.pending_confirm = {"token": d["token"], "action": d["action"], "target": d["target"], "retry": retry}
    text = (_t("confirm_delete", lang, file=shown) if d["action"] == "file_delete"
            else _t("confirm_forget", lang, fact=shown or d["target"]) if d["action"] == "memory_delete"
            else f"Confirm {d['action'].replace('_', ' ')} on {shown}? Confirm or cancel.")
    return _Reply(text, intent, action=d["action"], confirmation={"token": d["token"], "action": d["action"], "target": d["target"]})


def _need(ctx: context.Context, intent: str, need: str, slots: dict, question: str, lang: str) -> _Reply:
    ctx.pending_slot = {"intent": intent, "need": need, "slots": slots}
    return _Reply(question, intent, action="clarify")


def _general_prompt(text: str, convo_id: int) -> str:
    """System prompt, user's name, recent turns and the new question as one prompt."""
    name = identity.get_name()
    parts = [llm.SYSTEM_PROMPT]
    if name:
        parts.append(f"The user's name is {name}.")
    turns = [m for m in context.history(convo_id)[:-1] if m["content"]][-8:]
    if turns:
        parts.append("Conversation so far:\n" + "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:600]}" for m in turns))
    parts.append(f"User: {text}\nAssistant:")
    return "\n\n".join(parts)


def _llm_answer(text: str, convo_id: int, lang: str, intent: str) -> _Reply:
    """General question answering: local or consented cloud model, then a Wikipedia lookup, then a search link."""
    if not llm.is_local() and not config.get_bool("cloud_consent"):
        return _Reply(_t("llm_blocked", lang, link=llm.search_link(text)), intent)
    if llm.get_provider() is None:
        return _wiki_or_link(text, lang, intent)
    res = llm.ask(_general_prompt(text, convo_id), timeout=llm.ANSWER_TIMEOUT, max_tokens=llm.ANSWER_TOKENS)
    if res.ok:
        # A plain chat model has no tools: it must not claim to have done anything.
        return _Reply(agent_native.guard_claims(res.data, []), intent, action="llm")
    if res.error_code == E_NO_API_KEY:
        return _wiki_or_link(text, lang, intent)
    return _Reply(_t("error", lang, reason=res.message.rstrip(".")) + " " + llm.search_link(text), intent)


def _wiki_or_link(text: str, lang: str, intent: str) -> _Reply:
    """No model is configured: with cloud consent try a free Wikipedia summary, else give a search link."""
    if config.get_bool("cloud_consent"):
        from adhyaksh.llm import wiki
        extract = wiki.lookup(text, lang)
        if extract:
            return _Reply(extract, intent, action="wiki")
    return _Reply(_t("llm_unavailable", lang, link=llm.search_link(text)), intent)


# Requests to act on the computer that no tool covers: never hand these to a chat model.
_UNSUPPORTED_ACTION = re.compile(
    r"\b(shut\s*down|shutdown|restart|reboot|log\s*off|sign\s*out|hibernate|uninstall|install|format|"
    r"send\s+(an?\s+)?(email|mail|message|sms)|call|dial|play|download)\b", re.IGNORECASE)
_TOOLISH = re.compile(
    r"\b(file|folder|directory|app|screenshot|excel|word|docx|xlsx|remember|forget|memory|status|cpu|ram|"
    r"disk|open|close|delete|create|rename|move|copy|search my|my documents)\b", re.IGNORECASE)


# Words that ask for knowledge or writing rather than an action on this computer.
_GENERAL_CUES = re.compile(
    r"\b(?:whats|wats|hows|whos|wheres|ketl\w+|kitn\w+|likh\w*|lakh\w*|sunao|kahani|shayari|joke|kavita|caption|essay|nibandh|matlab|"
    r"suggest|explain|describe|define|write|compose|translate|summari[sz]e|suggest|recommend|tips?|ideas?|advice|"
    r"difference\s+between|meaning\s+of|compare|why|how|who|whom|whose|which|when|where|what|"
    r"samjh?ao|samjavo|samjha|kyun|kyu|kaise|kisne|kaun|kab|kahan|kitna|kitni|kitne|kem|kevi|kevo|koe|kone|kyare|"
    r"ketlo|ketli|ketlu|shu|kon|jaankari|jankari|vishe|baare\s+mein)\b"
    r"|सुनाओ|कहानी|कविता|चुटकुला|जोक|बताओ|लिखो|જોક|વાર્તા|કવિતા|શાયરી|કહો|લખો|સંભળાવો|समझाओ|समझाइए|क्यों|कैसे|कौन|किसने|कब|कहाँ|कितना|कितनी|कितने|क्या\s+होता|के\s+बारे\s+में|"
    r"સમજાવો|કેમ|કેવી|કોણ|ક્યારે|ક્યાં|કેટલો|કેટલી|કેટલું|વિશે", re.IGNORECASE)

# Lexical evidence that a tool-style intent really was asked for. Without any, a question is general knowledge.
_INTENT_SIGNAL = {
    "system_status": re.compile(r"cpu|ram\b|disk|storage|memory|battery|processor|laptop|computer|\bpc\b|system|"
                                r"सीपीयू|रैम|डिस्क|सिस्टम|લેપટોપ|સિસ્ટમ|રેમ|ડિસ્ક|सीपीयू|मेमोरी|મેમરી", re.IGNORECASE),
    "time_date": re.compile(r"\btime\b|\bdate\b|\bday\b|clock|baje|baja|vagya|vaage|vaag|tarikh|tareekh|din\b|vaar|"
                            r"समय|तारीख|बजे|दिन|સમય|તારીખ|વાગ્યા|દિવસ|વાર", re.IGNORECASE),
    "memory_recall": re.compile(r"\bmy\b|\bmine\b|\bmera\b|\bmeri\b|\bmaru\b|\bmaro\b|\bmari\b|\bmaine\b|\bme\b|"
                                r"remember|recall|yaad|याद|मेरा|मेरी|मैंने|મારો|મારી|મારું|મેં|યાદ", re.IGNORECASE),
    "greet": re.compile(r"\b(?:hello|hi|hey|namaste|namaskar|morning|evening|afternoon|kem\s+ch+o)\b|नमस्|હેલો|નમસ્|કેમ\s+છો",
                        re.IGNORECASE),
    "help": re.compile(r"\bhelp\b|\bcommands?\b|\bfeatures?\b|madad|मदद|મદદ|what\s+can\s+you|kya\s+kar\s+sakte|"
                       r"how\s+(?:do|to)\s+i\s+use", re.IGNORECASE),
    "bot_identity": re.compile(r"\byou(?:r)?\b|\btum\b|\baap\b|\btame\b|\btu\b|तुम|आप|તમે|તું", re.IGNORECASE),
    "get_identity": re.compile(r"\bname\b|\bnaam\b|नाम|નામ|\bwho\s+am\s+i\b", re.IGNORECASE),
    "web_open": re.compile(r"\bopen\b|\bgo\s+to\b|\bsearch\b|\.com|\.in\b|kholo|खोलो|ખોલો|browse|website", re.IGNORECASE),
    "doc_question": re.compile(r"document|\bpdf\b|\bfile\b|report|attach|दस्तावेज़|दस्तावेज|પીડીએફ|દસ્તાવેજ|फाइल|ફાઇલ|docs?\b",
                               re.IGNORECASE),
    "vision_detect": re.compile(r"photo|image|picture|camera|webcam|detect|object|vision|tasveer|तस्वीर|फोटो|इमेज|कैमरा|"
                                r"ફોટો|તસવીર|ઇમેજ|કેમેરા", re.IGNORECASE),
    "pc_performance": re.compile(r"perform|boost|faster|\bfast\b|speed|lag|hang|\bram\b|memory|process|clean|cpu|slow|"
                                 r"tez|तेज|धीमा|परफॉर्म|रैम|मेमोरी|પરફોર્મ|ઝડપી|રેમ|મેમરી|હેંગ", re.IGNORECASE),
    "voice_control": re.compile(r"listen|voice|hands.?free|wake|speak|talk|quiet|mute|aloud|\bmic\b|sunn|sambh|chup|bol|"
                                r"सुन|बोल|चुप|आवाज|माइक|સાંભળ|બોલ|ચૂપ|અવાજ|માઇક", re.IGNORECASE),
    "ocr_read": re.compile(r"text|read|written|sign|ocr|words|likh|lakh|padh|vanch|टेक्स्ट|लिख|पढ़|લખ|વાંચ|ટેક્સ્ટ", re.IGNORECASE),
    "process_list": re.compile(r"process|program|\bapps?\b|\bram\b|memory|cpu|running|chal|task|प्रोग्राम|प्रोसेस|रैम|પ્રોગ્રામ|પ્રોસેસ|રેમ",
                               re.IGNORECASE),
    "process_kill": re.compile(r"kill|process|terminate|end\s+task|force|band|bandh|बंद|ખતમ|બંધ|प्रोसेस|પ્રોસેસ", re.IGNORECASE),
    "reminder_set": re.compile(r"remind|alarm|wake|yaad\s+dila|yaad\s+apav|याद\s+दिला|अलार्म|रिमाइंडर|યાદ\s+અપાવ|એલાર્મ|રિમાઇન્ડર",
                               re.IGNORECASE),
    "reminder_list": re.compile(r"reminder|alarm|रिमाइंडर|अलार्म|રિમાઇન્ડર|એલાર્મ", re.IGNORECASE),
    "reminder_cancel": re.compile(r"reminder|alarm|रिमाइंडर|अलार्म|રિમાઇન્ડર|એલાર્મ", re.IGNORECASE),
    "clipboard_read": re.compile(r"clip\s*board|cop(?:y|ied)|क्लिपबोर्ड|કોપી|ક્લિપબોર્ડ|कॉपी", re.IGNORECASE),
    "clipboard_write": re.compile(r"clip\s*board|copy|क्लिपबोर्ड|कॉपी|ક્લિપબોર્ડ|કોપી", re.IGNORECASE),
    "source_list": re.compile(r"source|document|file|notebook|attach|upload|सोर्स|दस्तावेज़|नोटबुक|સોર્સ|દસ્તાવેજ|નોટબુક", re.IGNORECASE),
    "source_summary": re.compile(r"source|document|file|notebook|attach|pdf|सोर्स|दस्तावेज़|फाइल|नोटबुक|સોર્સ|દસ્તાવેજ|ફાઇલ|નોટબુક", re.IGNORECASE),
    "source_delete": re.compile(r"source|notebook|सोर्स|नोटबुक|સોર્સ|નોટબુક", re.IGNORECASE),
    "app_open": re.compile(r"\bopen\b|launch|\bstart\b|\brun\b|kholo|khol\b|chalu|shuru|खोल|चालू|शुरू|ખોલ|ચાલુ|શરૂ",
                           re.IGNORECASE),
    "app_close": re.compile(r"close|quit|exit|kill|stop|band|bandh|off\b|बंद|બંધ", re.IGNORECASE),
    "out_of_scope": re.compile(r"$^"),
    "unknown": re.compile(r"$^"),
}


# Phrases that are about knowledge even when a tool-like word (ram, file, memory) appears in them.
_STRONG_KNOWLEDGE = re.compile(r"\b(?:difference\s+between|meaning\s+of|full\s+form\s+of|history\s+of|what\s+is\s+an?\s|"
                               r"what\s+are\s|who\s+(?:was|is|invented|discovered)\b|explain\s+what|write\s+(?:a|an|me|some|one|two)\b|"
                               r"likh\s+do\b|likho\b|lakhi\s+(?:do|apo)\b)", re.IGNORECASE)


def _is_general_question(text: str) -> bool:
    """A question or request for knowledge or writing, not a tool."""
    if _STRONG_KNOWLEDGE.search(text) and not router._has_file_extension(text) and not _UNSUPPORTED_ACTION.search(text):
        return True
    if _TOOLISH.search(text) or _UNSUPPORTED_ACTION.search(text):
        return False
    return _is_question(text) or bool(_GENERAL_CUES.search(text))


def _general_override(text: str, intent: str) -> bool:
    """True when the model picked a tool-style or catch-all intent that nothing in the text supports,
    while the text reads as a general knowledge request. Intents with concrete tool evidence keep priority."""
    sig = _INTENT_SIGNAL.get(intent)
    return sig is not None and _is_general_question(text) and not sig.search(text)


_KILL = re.compile(r"\b(?:kill|terminate|end)\b", re.IGNORECASE)


def _vision_reply(text: str, slots: dict, ctx: context.Context, c: dict) -> _Reply:
    """Describe an attached image (objects, positions, sizes, colours; named or small objects on request), read its
    text when asked, or open the Object Detection page, or say how to give an image."""
    if ctx.images and router._OCR.search(text or ""):
        return _ocr_reply(text, {}, ctx, c)
    if ctx.images:
        res = features.analyze_image(ctx.images[0], text, ctx=c)
        if not res.ok:
            return _Reply("I could not analyse that image: " + res.message.rstrip(".") + ".", "vision_detect", action="vision")
        d = res.data
        lines = [d["summary"]]
        for a in d.get("requested", []):
            if a["found"]:
                lines.append(f"Yes, I can see a {a['name']}.")
            elif not a["known"]:
                lines.append(f"I cannot look for '{a['name']}': it is not one of the 80 object types I know, and the "
                             "open-vocabulary model is not installed.")
            else:
                lines.append(f"I do not see a {a['name']}.")
        if not d["total"] and d.get("guesses"):
            lines.append("Best guess for the whole picture: " + ", ".join(f"{g['label']} ({g['confidence']:.0%})" for g in d["guesses"]) + ".")
        if d.get("mode") == "tiled":
            lines.append("(Scanned in tiles to find small objects.)")
        return _Reply("\n".join(lines), "vision_detect", action="vision")
    if slots.get("open"):
        res = features.open_page("vision", ctx=c)
        if res.ok:
            return _Reply("Opening the Object Detection page.", "vision_detect", action="open_page",
                          extra={"open_page": "vision"})
    return _Reply("Attach a photo to your message (paperclip) and I will list the objects in it, or open the "
                  "Object Detection page to use the camera.", "vision_detect", action="vision")


def _ocr_reply(text: str, slots: dict, ctx: context.Context, c: dict) -> _Reply:
    """Read printed text from an attached image, or from the screen when asked."""
    image, source = (ctx.images[0] if ctx.images else None), "image"
    if image is None and slots.get("screen"):
        shot = system.screenshot(ctx=c)
        if not shot.ok:
            return _Reply("I could not take a screenshot to read: " + shot.message.rstrip(".") + ".", "ocr_read", action="ocr")
        image, source = Path(shot.data["path"]).read_bytes(), "screen"
    if image is None:
        return _Reply("Attach a photo or screenshot (paperclip) and ask me to read the text in it, or say: read the text on my screen.",
                      "ocr_read", action="ocr")
    res = features.read_text(image, ctx=c)
    if not res.ok:
        return _Reply("I could not read text: " + res.message.rstrip(".") + ".", "ocr_read", action="ocr")
    if not res.data["text"].strip():
        return _Reply("I could not find printed text in that " + source + ". Hindi and Gujarati script need Tesseract "
                      "with the hin and guj language data.", "ocr_read", action="ocr")
    return _Reply(f"Text in the {source}:\n" + res.data["text"], "ocr_read", action="ocr")


def _performance_reply(text: str, slots: dict, ctx: context.Context, lang: str, c: dict, intent: str) -> _Reply:
    kind = slots.get("kind", "hogs")
    if kind == "page":
        res = features.open_page("performance", ctx=c)
        if res.ok:
            return _Reply("Opening the PC Performance page.", intent, action="open_page", extra={"open_page": "performance"})
    if kind == "kill":
        return _Reply("I do not stop processes by name. Say 'close <application>' for allow-listed apps, "
                      "or ask 'which apps use the most RAM' to see the heaviest ones.", intent, action="performance")
    if kind == "boost":
        scan = features.temp_scan(ctx=c)
        if not scan.ok:
            return _Reply(_error_reply(scan, lang), intent, action="performance")
        if not scan.data["files"]:
            return _Reply("There are no old temp files to clean. Your PC is already tidy.", intent, action="performance")
        res = features.temp_clean(ctx=c)
        if res.error_code == E_NEEDS_CONFIRM:
            r = _confirm_reply(res, lang, ctx, lambda tok: features.temp_clean(ctx=_ctx_for(text, intent, tok), token=tok),
                               intent, "temp files")
            r.text = (f"Found {scan.data['mb']} MB in {scan.data['files']} temp files older than a day. "
                      "Confirm to delete them or cancel.")
            return r
        return _Reply(_error_reply(res, lang) if not res.ok else f"Cleaned {res.data['mb']} MB.", intent, action="performance")
    res = features.perf_report(ctx=c)
    if not res.ok:
        return _Reply(_error_reply(res, lang), intent, action="performance")
    d = res.data
    top = ", ".join(f"{p['name']} ({p['ram_percent']}%)" for p in d.get("top", []))
    return _Reply(f"CPU {d['cpu_percent']:.0f}%, RAM {d['ram_percent']:.0f}% ({d['ram_available_gb']:.1f} GB free), "
                  f"disk {d['disk_percent']:.0f}% ({d['disk_free_gb']:.1f} GB free)."
                  + (f" Using the most memory: {top}." if top else ""), intent, action="performance")


_VOICE_TEXT = {
    "start": "Hands-free listening is on. Your browser may ask for microphone permission. Say 'stop listening' to end it.",
    "stop": "Listening stopped.", "quiet": "I will stop talking.",
    "speak_on": "I will read my replies aloud.", "speak_off": "I will stop reading replies aloud.",
    "wake_on": "Wake word is on: say 'Adhyaksh' before a command in hands-free mode.",
    "wake_off": "Wake word is off: hands-free mode acts on everything it hears.",
}


def _voice_reply(text: str, slots: dict, c: dict, intent: str) -> _Reply:
    action = slots.get("action")
    if not action:
        parsed = router.voice_action(text)
        action, slots = (parsed[0], {"value": parsed[1]}) if parsed else ("start", {})
    res = features.voice_command(action, slots.get("value", ""), ctx=c)
    if not res.ok:
        return _Reply("I could not change the voice setting: " + res.message.rstrip(".") + ".", intent, action="voice")
    msg = (f"Voice language set to {features.VOICE_LANGS[slots['value']]}." if action == "lang"
           else _VOICE_TEXT[action])
    return _Reply(msg, intent, action="voice", extra={"voice_cmd": {"action": action, "value": slots.get("value", "")}})


def _dispatch(intent: str, text: str, slots: dict, ctx: context.Context, convo_id: int, lang: str,
              mode: str = "cowork") -> _Reply:
    c = _ctx_for(text, intent)
    if mode == "chat" and intent in OS_INTENTS:
        return _Reply(_t("needs_cowork", lang), intent, action="needs_cowork", suggest_mode="cowork")
    if intent == "vision_detect":
        return _vision_reply(text, slots, ctx, c)
    if intent == "ocr_read":
        return _ocr_reply(text, slots, ctx, c)
    if intent == "pc_performance":
        return _performance_reply(text, slots, ctx, lang, c, intent)
    if intent == "voice_control":
        return _voice_reply(text, slots, c, intent)
    if intent == "greet":
        return _Reply(_t("greet", lang), intent)
    if intent == "bot_identity":
        return _Reply("I am ADHYAKSH.", "bot_identity")
    if intent == "smalltalk":
        kind = slots.get("kind", "thanks")
        if kind == "thanks":
            return _Reply(_t("smalltalk_thanks", lang), "smalltalk")
        if kind == "bye":
            return _Reply(_t("smalltalk_bye", lang), "smalltalk")
        return _Reply(_t("smalltalk_how_are_you", lang), "smalltalk")
    if intent == "time_date":
        now = datetime.now()
        kind = slots.get("kind") or _time_date_kind(text)
        if "time" in kind:
            return _Reply(_t("time_now", lang, time=now.strftime("%I:%M %p")), "time_date")
        return _Reply(_t("date_today", lang, date=now.strftime("%d %B %Y")), "time_date")
    if intent == "math":
        return _Reply(_t("math", lang, expr=slots["expr"], value=slots["value"]), "math")
    if intent == "help":
        return _Reply(_t("help", lang), intent)
    if intent == "set_identity":
        name, conf = (slots.get("name"), slots.get("conf", 0)) if slots.get("name") else identity.extract_name(text)
        if not name:
            if _is_general_question(text):  # "tell me a joke" in any language is a request, not a name
                return _llm_answer(text, convo_id, lang, "knowledge_question")
            # A statement without a name is not an identity declaration (e.g. "Current time is 10:15 AM").
            return _Reply(_t("unknown", lang), "unknown")
        if conf >= 0.75:
            identity.save_name(name)
            return _Reply(_t("identity_saved", lang, name=name), intent, action="profile")
        ctx.pending_name = name
        return _Reply(_t("ask_name", lang, name=name), intent, action="clarify")
    if intent == "get_identity":
        if not _is_question(text) and not router._ID_QUERY.search(text):
            return _Reply(_t("unknown", lang), "unknown")
        name = identity.get_name()
        return _Reply(_t("identity_query", lang, name=name) if name else _t("no_name", lang), intent)
    if intent == "memory_save":
        if slots.get("ask"):
            return _need(ctx, intent, "content", {}, _t("ask_memory", lang), lang)
        res = store.save_fact(slots.get("fact") or slots.get("content") or text)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent)
        if res.data.get("updated"):
            return _Reply(_t("memory_updated", lang, fact=res.data["fact"], previous=res.data["previous"]), intent, action="memory")
        key = "memory_exists" if res.data["duplicate"] else "memory_saved"
        return _Reply(_t(key, lang, fact=res.data["fact"]), intent, action="memory")
    if intent == "volume_control":
        device, op = slots.get("device") or "speaker", slots.get("op")
        res = audio.control(op, device, slots.get("level"), ctx=c)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent, action="volume_control")
        d = res.data
        name = "microphone" if device == "mic" else "volume"
        key = {"mute": "muted", "unmute": "unmuted"}.get(op, "level_set")
        return _Reply(_t(f"volume_{key}", lang, name=name, level=d.get("level")), intent, action="volume_control")
    if intent == "brightness_control":
        res = display.control(slots.get("op"), slots.get("level"), ctx=c)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent, action="brightness_control")
        return _Reply(_t("brightness_set", lang, level=res.data["level"]), intent, action="brightness_control")
    if intent == "memory_forget":
        res = store.forget(text, ctx=c)
        if res.error_code == E_NEEDS_CONFIRM:
            return _confirm_reply(res, lang, ctx, lambda tok: store.forget(text, ctx=_ctx_for(text, intent, tok)), intent,
                                  res.data.get("target", "") if isinstance(res.data, dict) else "")
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent, action="memory")
        return _Reply(_t("memory_forgotten", lang, fact=res.data["fact"]), intent, action="memory")
    if intent == "memory_recall":
        if slots.get("all") or router.match_memory(text) == router.Rule("memory_recall", {"all": True}):
            facts = store.list_facts()
            if not facts:
                return _Reply(_t("memory_none", lang), intent)
            lines = "\n".join(f"- {f['fact'][:300]}" for f in facts[:20])
            more = f"\n(and {len(facts) - 20} more)" if len(facts) > 20 else ""
            return _Reply(f"I remember {len(facts)} item(s):\n{lines}{more}", intent, action="memory")
        res = store.recall(text)
        return _Reply(_t("memory_recall", lang, answer=res.data["answer"]) if res.ok else _t("memory_none", lang), intent)
    if intent == "system_status":
        res = system.status(ctx=c)
        d = res.data
        return _Reply(_t("status", lang, cpu=d["cpu"], ram=d["ram"], disk=d["disk"]) if res.ok else _error_reply(res, lang),
                      intent, action="system_status")
    if intent == "folder_create":
        folder = slots.get("folder") or router.find_folder_name(text)
        if not folder:
            return _need(ctx, intent, "folder", slots, _t("ask_folder", lang), lang)
        res = files.create_folder(folder, ctx=c)
        return _Reply(_t("folder_created", lang, path=res.data["path"]) if res.ok else _error_reply(res, lang),
                      intent, action="folder_create")
    if intent == "screenshot":
        res = system.screenshot(ctx=c)
        if res.ok:
            return _Reply(_t("screenshot_taken", lang, path=res.data["path"]), "screenshot",
                          action="screenshot")
        return _Reply(_t("error", lang, reason=res.message.rstrip(".") or "unknown error"), "screenshot")
    if intent == "special_folder_open":
        folder = slots.get("folder") or router.find_special_folder(text)
        if not folder:
            return _need(ctx, intent, "folder", slots, _t("ask_folder", lang), lang)
        res = system.open_special_folder(folder, ctx=c)
        if res.ok:
            return _Reply(_t("special_folder_opened", lang, folder=folder),
                          "special_folder_open", action="special_folder_open")
        return _Reply(_t("error", lang, reason=res.message.rstrip(".") or "unknown error"),
                      "special_folder_open")
    if intent == "web_open":
        url = slots.get("url")
        if not url:
            # Model path: try the shared parser before giving up.
            parsed = router.parse_web_command(text)
            url = parsed.slots.get("url") if parsed else None
        if not url:
            # Web verb present but no site/query: keep a pending slot and ask.
            return _need(ctx, intent, "url", slots,
                         _t("ask_web_url", lang), lang)
        url = entities.normalize_url(url)
        res = system.web_open(url, ctx=c)
        if res.ok:
            return _Reply(_t("web_opened", lang, url=url), "web_open", action="web_open")
        return _Reply(_t("error", lang, reason=res.message.rstrip(".") or "unknown error"), "web_open")
    if intent in ("app_open", "app_close"):
        app = slots.get("app") or router.find_app(text) or (ctx.last_app if router.has_pronoun(text) else None)
        if not app:
            return _need(ctx, intent, "app", slots, _t("ask_app", lang), lang)
        ctx.last_app = app
        if intent == "app_open":
            res = apps.open_app(app, ctx=c)
            if res.ok:
                return _Reply(_t("app_opened", lang, app=app), intent, action="app_open")
            if res.error_code == E_BLOCKED:
                return _Reply(_t("app_refused", lang, app=app), intent, action="app_open")
            return _Reply(_t("error", lang, reason=app + ": " + res.message.rstrip(".") or "unknown error"),
                          intent, action="app_open")
        res = apps.close_app(app, ctx=c)
        if res.error_code == E_NEEDS_CONFIRM:
            return _confirm_reply(res, lang, ctx, lambda tok, a=app: apps.close_app(a, ctx=_ctx_for(text, intent, tok)), intent, app)
        if res.ok and (res.data or {}).get("waiting") and not res.data.get("closed"):
            return _Reply(_t("app_close_waiting", lang, app=app), intent, action="app_close")
        return _Reply(_t("app_closed", lang, app=app) if res.ok else (
            _t("app_refused", lang, app=app) if res.error_code == E_BLOCKED else _error_reply(res, lang)), intent, action="app_close")
    if intent == "office_create":
        kind = router.office_kind(text)
        name = router.find_file(text)
        if kind == "xlsx":
            if re.search(r"names?|naam|नाम", text, re.IGNORECASE) or not name:
                res = (office.names_example(router.find_count(text), ctx=c) if not name else
                       office.create_workbook(name, [[n] for n in office.INDIAN_NAMES[:router.find_count(text)]], ctx=c))
            else:
                res = office.create_workbook(name, [[]], ctx=c)
            if not res.ok:
                return _Reply(_error_reply(res, lang), intent, action="office_create")
            d = res.data
            return _Reply(_t("office_created", lang, name=d["path"].replace("\\", "/").split("/")[-1], rows=d["rows"], folder=d["folder"]),
                          intent, action="office_create")
        res = office.create_document(name or "document.docx", [router.find_content(text) or ""], ctx=c)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent, action="office_create")
        return _Reply(_t("doc_created", lang, name=res.data["path"].replace("\\", "/").split("/")[-1], folder=res.data["folder"]),
                      intent, action="office_create")
    if intent in ("file_create", "file_read", "file_update", "file_delete", "file_search"):
        return _file_intent(intent, text, slots, ctx, lang, c)
    if intent in COWORK_INTENTS:
        return _cowork_reply(intent, text, slots, ctx, lang, c)
    if intent in ("source_list", "source_summary", "source_delete"):
        return _sources_reply(intent, text, slots, ctx, lang, c)
    if intent == "doc_question":
        res = answerer.answer(text)
        if res.data.get("found"):
            return _Reply(res.data["answer"], intent, action="doc_answer", sources=res.data["sources"])
        # No indexed documents or below the retrieval threshold -> knowledge answerer.
        return _llm_answer(text, convo_id, lang, "knowledge_question")
    if intent == "knowledge_question":
        return _llm_answer(text, convo_id, lang, intent)
    if intent == "out_of_scope":
        if llm.available() and not _UNSUPPORTED_ACTION.search(text):
            return _llm_answer(text, convo_id, lang, "knowledge_question")
        return _Reply(_cannot_do_yet(lang), "out_of_scope")
    return _Reply(_cannot_do_yet(lang), "unknown")


def _file_intent(intent: str, text: str, slots: dict, ctx: context.Context, lang: str, c: dict) -> _Reply:
    f = slots.get("file") or router.find_file(text)
    if not f and (slots.get("reference") or router.has_pronoun(text)) and ctx.last_file:
        f = ctx.last_file
    if intent == "file_search":
        q = f or " ".join(w for w in re.findall(r"[\w.]+", text) if len(w) > 3 and w.lower() not in
                          {"search", "find", "files", "file", "named", "where", "look", "this", "that"})
        if not q:
            return _need(ctx, intent, "file", slots, _t("ask_filename", lang), lang)
        res = files.search(q, ctx=c)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent, action="file_search")
        m = res.data["matches"]
        return _Reply(_t("file_found", lang, count=len(m), items="\n".join(m)) if m else _t("file_none", lang, query=q),
                      intent, action="file_search")
    if not f:
        return _need(ctx, intent, "file", slots, _t("ask_filename", lang), lang)
    if intent == "file_create":
        if f and "." not in Path(f).name:
            f = f + ".txt"
        res = files.create(f, router.find_content(text) or "", ctx=c)
        if res.ok:
            ctx.last_file = res.data["path"]
        return _Reply(_t("file_created", lang, path=res.data["path"]) if res.ok else _error_reply(res, lang), intent, action="file_create")
    if intent == "file_read":
        res = files.read(f, ctx=c)
        if res.ok:
            ctx.last_file = res.data["path"]
        return _Reply(_t("file_read", lang, path=res.data["path"], content=res.data["content"] or "(empty)") if res.ok
                      else _error_reply(res, lang), intent, action="file_read")
    if intent == "file_update":
        content = slots.get("content") or router.find_content(text)
        if not content:
            return _need(ctx, intent, "content", {**slots, "file": f}, "What text should I write?", lang)
        mode = "overwrite" if re.search(r"overwrite|replace", text, re.IGNORECASE) else "append"
        res = files.update(f, content, mode, ctx=c)
        if res.error_code == E_NEEDS_CONFIRM:
            return _confirm_reply(res, lang, ctx, lambda tok: files.update(f, content, mode, ctx=_ctx_for(text, intent, tok)), intent, f)
        if res.ok:
            ctx.last_file = res.data["path"]
        return _Reply(_t("file_updated", lang, path=res.data["path"]) if res.ok else _error_reply(res, lang), intent, action="file_update")
    res = files.delete(f, ctx=c)  # file_delete
    if res.error_code == E_NEEDS_CONFIRM:
        shown = res.data["target"]
        return _confirm_reply(res, lang, ctx, lambda tok: files.delete(f, ctx=_ctx_for(text, intent, tok)), intent, shown)
    return _Reply(_t("file_deleted", lang, path=res.data["path"]) if res.ok else _error_reply(res, lang), intent, action="file_delete")


def _finish_confirmation(ctx: context.Context, accept: bool, lang: str) -> _Reply:
    p, ctx.pending_confirm = ctx.pending_confirm, None
    if not accept:
        policy.cancel_guarded(p["token"])
        return _Reply(_t("cancelled", lang), "confirmation", action="cancel")
    res = p["retry"](p["token"])
    if not res.ok:
        return _Reply(_error_reply(res, lang), "confirmation", action=p["action"])
    d = res.data or {}
    if p["action"] == "file_delete":
        ctx.last_file = None
        return _Reply(_t("file_deleted", lang, path=d.get("path", p["target"])), "confirmation", action=p["action"])
    if p["action"] == "memory_delete":
        return _Reply(_t("memory_forgotten", lang, fact=d.get("fact", p["target"])), "confirmation", action=p["action"])
    if p["action"] == "process_kill":
        return _Reply(f"Ended {d.get('name', p['target'])} ({d.get('ended', 0)} process(es), about {d.get('freed_mb', 0)} MB freed).",
                      "confirmation", action=p["action"])
    if p["action"] == "reminder_cancel_all":
        return _Reply(f"Cancelled {d.get('cancelled', 0)} reminder(s).", "confirmation", action=p["action"])
    if p["action"] == "source_delete":
        return _Reply(f"Removed the source {d.get('file', p['target'])}.", "confirmation", action=p["action"])
    if p["action"] == "temp_clean":
        return _Reply(f"Cleaned {d.get('mb', 0)} MB of temp files. Skipped {d.get('skipped', 0)} files in use.",
                      "confirmation", action=p["action"])
    if p["action"] == "file_overwrite":
        return _Reply(_t("file_updated", lang, path=d.get("path", p["target"])), "confirmation", action=p["action"])
    return _Reply(_t("app_closed", lang, app=d.get("app", p["target"])), "confirmation", action=p["action"])


def confirm(conversation_id: int, accept: bool) -> Result:
    """Called by the UI confirmation card buttons."""
    ctx = context.get(conversation_id)
    if not ctx.pending_confirm and not ctx.pending_agent_confirm:
        return Result.failure(E_BLOCKED, "There is nothing to confirm.")
    if ctx.pending_agent_confirm:
        r = _finish_agent_confirmation(ctx, accept, conversation_id, "en")
        context.save_message(conversation_id, "assistant", r.text, r.intent, 1.0, 0.0)
        return Result.success({"reply": r.text, "intent": r.intent, "action": r.action, "confirmation": None})
    r = _finish_confirmation(ctx, accept, "en")
    context.save_message(conversation_id, "assistant", r.text, r.intent, 1.0, 0.0)
    return Result.success({"reply": r.text, "intent": r.intent, "action": r.action, "confirmation": None})


def _process(text: str, ctx: context.Context, convo_id: int, lang: str, mode: str = "cowork") -> _Reply:
    low = text.strip().casefold().rstrip(".!")
    answer = speech.yes_no(text)  # True, False or None; accepts spoken forms in five language styles
    if ctx.pending_agent_confirm and answer is not None:
        return _finish_agent_confirmation(ctx, answer, convo_id, lang)
    if ctx.pending_confirm and answer is not None:
        return _finish_confirmation(ctx, answer, lang)
    if (ctx.pending_confirm or ctx.pending_agent_confirm) and len(text.split()) <= 2 and not router.understand(text):
        # A very short unclear reply ("hmm", "what?") while a confirmation is open: ask again, never guess.
        return _Reply("Please say yes to confirm or no to cancel.", "confirmation", action="clarify")
    if ctx.pending_name and answer is not None:
        name, ctx.pending_name = ctx.pending_name, None
        if answer:
            identity.save_name(name)
            return _Reply(_t("identity_saved", lang, name=name), "set_identity", action="profile")
        return _Reply(_t("cancelled", lang), "set_identity")
    if ctx.pending_agent_ask:
        # The agent asked a clarifying question: this message is the answer (unless the user drops the request).
        p, ctx.pending_agent_ask = ctx.pending_agent_ask, None
        if low in _DROP_REQUEST:
            agent_native.cancel_ask(p["token"])
            return _Reply(_t("cancelled", lang), "agent_ask", action="cancel")
        return _native_reply(agent_native.answer(p["token"], text), ctx, p["text"])
    # Explicit agent invocation: "agent: <request>"
    if low.startswith("agent:"):
        return _agent_dispatch(low[len("agent:"):].strip(), ctx, convo_id, lang)
    ctx.pending_confirm = None
    ctx.pending_agent_confirm = None
    ctx.pending_name = None
    ctx.agent_steps = None
    if ctx.pending_slot:
        p, ctx.pending_slot = ctx.pending_slot, None
        if low in NO or answer is False and len(text.split()) <= 3:
            return _Reply(_t("cancelled", lang), p["intent"])
        slots = dict(p["slots"])
        if p["need"] == "file":
            slots["file"] = router.find_file(text) or router.clean_slot_name(text)
        elif p["need"] == "app":
            slots["app"] = router.find_app(text) or text.strip()
        elif p["need"] == "folder":
            slots["folder"] = router.clean_slot_name(text)
        elif p["need"] == "url":
            slots["url"] = router.extract_web_url(text)
        elif p["need"] == "when":
            # "When should I remind you?" answered: combine the saved text with the time just given.
            return _dispatch("reminder_set", f"remind me to {p['slots'].get('text', 'Reminder')} {text}", {}, ctx, convo_id, lang, mode=mode)
        elif p["need"] == "target":
            slots["target"] = text.strip()
        elif p["need"] == "reminder":
            slots["query"] = text.strip()
        elif p["need"] == "source":
            slots["name"] = text.strip()
        else:
            slots["content"] = text.strip()
        return _dispatch(p["intent"], text, slots, ctx, convo_id, lang, mode=mode)
    negated = frames.negated_command(text)
    if negated is not None:
        # "don't open notepad", "chrome band mat karo": never executed, on any path (rules, classifier or model).
        return _negated_reply(negated, lang)
    if agent_native.available():
        fast = frames.command(text) if config.get("routing") == "local_first" else None
        if fast is not None:
            # A complete, unambiguous single command: run it here, without a model round trip (faster, works
            # offline, and nothing is sent to a cloud model).
            return _dispatch(fast.intent, text, fast.slots(), ctx, convo_id, lang, mode=mode)
        # A language model is usable: the tool-calling agent handles the request. Rules and the classifier
        # below are the offline fallback (also used when the model cannot be reached).
        r = _native_dispatch(text, ctx, convo_id, lang, mode)
        if r is not None:
            return r
    steps = router.split_steps(text)
    if steps:
        return _run_steps(steps, ctx, convo_id, lang, mode)
    rule = router.understand(text)
    if rule:
        intent, slots = _correct_file_folder(rule.intent, rule.slots, text)
        return _dispatch(intent, text, slots, ctx, convo_id, lang, mode=mode)
    hit = _context_answer(text, ctx, lang)
    if hit:
        return hit
    intent, conf, gap = registry.predict(text)
    cleaned = router.clean_command(text)
    if cleaned != text:
        c_intent, c_conf, c_gap = registry.predict(cleaned)
        if c_conf > conf:
            intent, conf, gap, text = c_intent, c_conf, c_gap, cleaned
    if intent == "unknown" and conf == 0.0 and not registry.available():
        return _Reply("No trained model is active. Run: python -m adhyaksh.nlu.train --all", "unknown", 0.0)
    threshold = config.get_float("confidence_threshold")
    if _general_override(text, intent):
        # Unsupported by the text: answer as a general question instead of running a tool intent.
        r = _dispatch("knowledge_question", text, {}, ctx, convo_id, lang, mode=mode)
        r.conf = conf
        return r
    agent_enabled = llm.available() and not llm.is_local()
    agree, note = factorized.cross_check(text, intent)
    if not agree:
        logging_setup.event("intent_conflict", intent=intent, note=note)
    if conf < threshold or gap < registry.MIN_GAP or not agree:
        # Low confidence or ambiguous (small gap between the top two intents): do not dispatch
        # to the nearest intent. A plain question goes to the general answerer; other requests use
        # the agent when enabled, else the knowledge answerer.
        if llm.available() and _is_general_question(text):
            r = _llm_answer(text, convo_id, lang, "knowledge_question")
            r.conf = conf
            return r
        if agent_enabled:
            return _agent_dispatch(text, ctx, convo_id, lang, mode)
        if llm.available() and not _UNSUPPORTED_ACTION.search(text):
            r = _llm_answer(text, convo_id, lang, "knowledge_question")
            r.conf = conf
            return r
        if _is_general_question(text):
            r = _llm_answer(text, convo_id, lang, "knowledge_question")
            r.conf = conf
            return r
        r = _Reply(_cannot_do_yet(lang), "unknown", conf, action="low_confidence")
        return r
    if _looks_multi_step(text) and agent_enabled:
        return _agent_dispatch(text, ctx, convo_id, lang, mode)
    # Model path: extract slots using the same extractors as the rule layer.
    intent, slots = _correct_file_folder(intent, _model_slots(intent, text), text)
    r = _dispatch(intent, text, slots, ctx, convo_id, lang, mode=mode)
    r.conf = conf
    return r


def _ingest_attachments(attachments: list[tuple[str, bytes]]) -> tuple[list[str], list[str], list[str]]:
    """Index attached files into the active notebook. Returns (ok lines, failure lines, indexed file names)."""
    from adhyaksh.rag import loader
    ok, bad, names = [], [], []
    for name, data in attachments:
        res = loader.ingest_bytes(name, data)
        if res.ok:
            ok.append(f"{res.data['filename']} ({res.data['chunks']} passages)")
            names.append(res.data["filename"])
        else:
            bad.append(f"{name}: {res.message.rstrip('.')}")
    return ok, bad, names


def _summary_text(data: dict) -> str:
    parts = [f"**{s['file']}**\n{s['summary']}" for s in data["summaries"]]
    return f"Summary of notebook {data['notebook']}:\n\n" + "\n\n".join(parts)


def _sources_reply(intent: str, text: str, slots: dict, ctx: context.Context, lang: str, c: dict) -> _Reply:
    """Notebook source commands: list, summarise, delete (delete needs confirmation)."""
    if intent == "source_list":
        res = sources.list_sources(ctx=c)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent)
        items = res.data["sources"]
        if not items:
            return _Reply(f"Notebook {res.data['notebook']} has no sources yet. Attach a document with the paperclip.", intent, action="sources")
        lines = "\n".join(f"{i + 1}. {s['file']} ({s['passages']} passages)" for i, s in enumerate(items))
        return _Reply(f"Notebook {res.data['notebook']} has {len(items)} source(s):\n{lines}", intent, action="sources")
    if intent == "source_summary":
        res = sources.summarize(slots.get("name"), ctx=c)
        return _Reply(_summary_text(res.data) if res.ok else _error_reply(res, lang), intent, action="sources")
    name = slots.get("name") or router.find_file(text)
    if not name:
        return _need(ctx, intent, "source", slots, "Which source should I remove?", lang)
    res = sources.delete_source(name, ctx=c)
    if res.error_code == E_NEEDS_CONFIRM:
        r = _confirm_reply(res, lang, ctx, lambda tok: sources.delete_source(name, ctx=_ctx_for(text, intent, tok), token=tok),
                           intent, res.data["target"])
        r.text = f"Remove the source {res.data['target']} from this notebook? Confirm or cancel."
        return r
    return _Reply(f"Removed the source {res.data['file']}." if res.ok else _error_reply(res, lang), intent, action="sources")


def _attachment_reply(text: str, ok: list[str], bad: list[str], ctx: context.Context,
                      convo_id: int, lang: str, mode: str, names: list[str] | None = None) -> _Reply:
    note = ""
    if ok:
        note += "Indexed: " + ", ".join(ok) + ".\n"
    if bad:
        note += "Could not index: " + "; ".join(bad) + ".\n"
    if not text:
        ctx.has_sources = ctx.has_sources or bool(ok)
        return _Reply(note.strip() + (" Ask me anything about it." if ok else ""), "attachment", action="attach")
    if ok and router.is_summary_request(text):
        res = sources.summarize(names[0] if names and len(names) == 1 else None, ctx=_ctx_for(text, "source_summary"))
        if res.ok:
            return _Reply(note + "\n" + _summary_text(res.data), "source_summary", action="sources")
    if ok:
        ctx.has_sources = True
        res = answerer.answer(text)
        if res.data.get("found"):
            return _Reply(note + "\n" + res.data["answer"], "doc_question", action="doc_answer",
                          sources=res.data["sources"])
        if router.understand(text) is None:
            # A question about the attachment that the attachment does not answer: say so instead of guessing a command.
            return _Reply(note + "\nI could not find that in the attached file. Try different words, or ask for a summary.",
                          "doc_question", action="doc_answer")
    r = _process(text, ctx, convo_id, lang, mode=mode)
    r.text = note + ("\n" if note else "") + r.text
    return r


def handle_message(text: str, conversation_id: int, voice: bool = False, mode: str = "cowork",
                   attachments: list[tuple[str, bytes]] | None = None) -> Result:
    """Process one user message and return reply, intent, confidence, action, timing.

    attachments: optional (filename, bytes) pairs; they are indexed and used for document Q&A."""
    t0 = time.perf_counter()
    text = (text or "").strip()[:MAX_MESSAGE]
    attachments = attachments or []
    if not text and not attachments:
        return Result.failure(E_LOW_CONFIDENCE, "Empty message.")
    lang = detect_lang(text) if text else "en"
    images = [d for n, d in attachments if Path(n).suffix.lower() in IMAGE_EXT]
    attachments = [(n, d) for n, d in attachments if Path(n).suffix.lower() not in IMAGE_EXT]
    names = [n for n, _ in attachments] + [f"image {i + 1}" for i in range(len(images))]
    shown = text
    if names:
        shown = (text + "\n" if text else "") + f"[Attached: {', '.join(names)}]"
    context.save_message(conversation_id, "user", shown)
    ctx = context.get(conversation_id)
    ctx.images = images or None
    try:
        if images and not attachments:
            r = _vision_reply(text, {}, ctx, _ctx_for(text, "vision_detect"))
        elif attachments:
            ok, bad, names = _ingest_attachments(attachments)
            r = _attachment_reply(text, ok, bad, ctx, conversation_id, lang, mode, names)
        else:
            r = _process(text, ctx, conversation_id, lang, mode=mode)
            if not r.intent.startswith("memory") and r.intent not in ("negated", "confirmation", "agent_confirm"):
                noticed = store.notice(text)  # only with the auto_memory setting on
                if noticed is not None and noticed.ok and not noticed.data.get("duplicate"):
                    logging_setup.event("memory_noticed", updated=bool(noticed.data.get("updated")))
    except Exception as exc:  # never raise to the UI for expected failures
        logging_setup.event("chat_error", logging.ERROR, exc_info=exc, lang=lang, mode=mode)
        r = _Reply(_t("error", lang, reason=f"internal error ({type(exc).__name__}); details are in the log on the Health page"),
                   "error", 0.0)
    finally:
        ctx.images = None
    ms = (time.perf_counter() - t0) * 1000
    logging_setup.event("chat_message", intent=r.intent, confidence=round(r.conf, 3), action=r.action or "",
                        lang=lang, mode=mode, voice=voice, ms=round(ms, 1))
    context.save_message(conversation_id, "assistant", r.text, r.intent, r.conf, ms)
    result = {"reply": r.text, "intent": r.intent, "confidence": round(r.conf, 3), "action": r.action,
              "latency_ms": round(ms, 1), "confirmation": r.confirmation, "sources": r.sources,
              "lang": lang, "voice": voice, "mode": mode}
    if r.suggest_mode is not None:
        result["suggest_mode"] = r.suggest_mode
    result.update(r.extra)
    return Result.success(result)


# ---------------------------------------------------------------------------
# Cowork handlers (P4): processes, reminders, clipboard, multi-step requests
# ---------------------------------------------------------------------------

def _cowork_reply(intent: str, text: str, slots: dict, ctx: context.Context, lang: str, c: dict) -> _Reply:
    if intent == "process_list":
        res = processes.list_processes(slots.get("top", 10), slots.get("sort", "memory"), ctx=c)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent)
        rows = res.data["processes"]
        key = "CPU" if res.data["sort"] == "cpu" else "memory"
        lines = "\n".join(f"{i + 1}. {r['name']}: {r['ram_mb']:.0f} MB, CPU {r['cpu_percent']:.0f}%"
                          + (f" ({r['count']} processes)" if r["count"] > 1 else "") for i, r in enumerate(rows))
        return _Reply(f"Top programs by {key} ({res.data['total']} running):\n{lines}\n"
                      "To end one, say for example: end task <name>.", intent, action="process_list")
    if intent == "process_kill":
        target = entities.clean_process_target(slots.get("target") or "")
        if not target:
            return _need(ctx, intent, "target", slots, "Which program should I end?", lang)
        res = processes.kill_process(target, ctx=c)
        if res.error_code == E_NEEDS_CONFIRM:
            r = _confirm_reply(res, lang, ctx, lambda tok: processes.kill_process(target, ctx=_ctx_for(text, intent, tok), token=tok),
                               intent, res.data["target"])
            r.text = f"End {res.data['target']}? Unsaved work in it will be lost. Confirm or cancel."
            return r
        if res.ok:
            return _Reply(f"Ended {res.data['name']}.", intent, action="process_kill")
        return _Reply(res.message, intent, action="process_kill")
    if intent == "reminder_set":
        res = reminders.add_natural(text, ctx=c)
        if not res.ok and res.data and res.data.get("need") == "when":
            return _need(ctx, intent, "when", {"text": res.data["text"]}, "When should I remind you?", lang)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent)
        return _Reply(f"Reminder set: {res.data['text']}, {res.data['when']}. I will remind you while ADHYAKSH is open.",
                      intent, action="reminder_set")
    if intent == "reminder_list":
        res = reminders.list_pending(ctx=c)
        items = res.data["reminders"] if res.ok else []
        if not items:
            return _Reply("You have no pending reminders.", intent, action="reminder_list")
        return _Reply("Your reminders:\n" + "\n".join(f"{i + 1}. {r['text']}, {r['when']}" for i, r in enumerate(items)),
                      intent, action="reminder_list")
    if intent == "reminder_cancel":
        if slots.get("all"):
            res = reminders.cancel(all_pending=True, ctx=c)
            if res.error_code == E_NEEDS_CONFIRM:
                r = _confirm_reply(res, lang, ctx, lambda tok: reminders.cancel(all_pending=True, ctx=_ctx_for(text, intent, tok), token=tok),
                                   intent, res.data["target"])
                r.text = f"Cancel all {res.data['target']}? Confirm or cancel."
                return r
            return _Reply(res.message if not res.ok else f"Cancelled {res.data['cancelled']} reminder(s).", intent, action="reminder_cancel")
        query = slots.get("query", "")
        if not query:
            pending = reminders.list_pending(ctx=c).data["reminders"]
            if len(pending) == 1:
                query = str(pending[0]["id"])
            elif not pending:
                return _Reply("You have no pending reminders.", intent)
            else:
                return _need(ctx, intent, "reminder", slots, "Which reminder should I cancel? Say a word from it.", lang)
        res = reminders.cancel(query, ctx=c)
        return _Reply(f"Cancelled the reminder: {res.data['text']}." if res.ok else res.message, intent, action="reminder_cancel")
    if intent == "clipboard_read":
        res = clipboard.read(ctx=c)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent)
        if res.data["empty"]:
            return _Reply("The clipboard has no text.", intent, action="clipboard_read")
        shown = res.data["text"][:600] + (" ..." if len(res.data["text"]) > 600 else "")
        return _Reply("Your clipboard has:\n" + shown, intent, action="clipboard_read")
    # clipboard_write
    value = slots.get("text") or router.find_content(text) or ""
    if not value:
        return _need(ctx, intent, "content", slots, "What should I copy to the clipboard?", lang)
    res = clipboard.write(value, ctx=c)
    return _Reply(f"Copied to the clipboard: {value[:200]}" if res.ok else _error_reply(res, lang), intent, action="clipboard_write")


def _run_steps(steps: list, ctx: context.Context, convo_id: int, lang: str, mode: str) -> _Reply:
    """Run each step in order through the normal handlers (each goes through the safety gateway). Stops at a step
    that needs a confirmation, an answer, or Cowork mode, and says which steps were not done."""
    lines, confirmation = [], None
    for i, (part, rule) in enumerate(steps):
        intent, slots = _correct_file_folder(rule.intent, rule.slots, part)
        r = _dispatch(intent, part, slots, ctx, convo_id, lang, mode=mode)
        lines.append(f"{i + 1}. {r.text}")
        if r.confirmation or r.action in ("clarify", "needs_cowork"):
            confirmation = r.confirmation
            rest = [p for p, _ in steps[i + 1:]]
            if rest:
                lines.append("Not done yet (ask again after this): " + "; ".join(rest) + ".")
            break
    return _Reply("\n".join(lines), "multi_step", action="multi_step", confirmation=confirmation)

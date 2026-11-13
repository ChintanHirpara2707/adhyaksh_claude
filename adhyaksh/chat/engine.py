"""Chat engine: message in, reply out. Rules, then the trained model, then tools via safety."""
from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

from adhyaksh import config, responses
from adhyaksh.chat import context, identity, router
from adhyaksh.agent import runner as agent_runner
from adhyaksh.llm import base as llm
from adhyaksh.memory import store
from adhyaksh.nlu import registry
from adhyaksh.rag import answerer
from adhyaksh.result import (E_BLOCKED, E_LOW_CONFIDENCE, E_NEEDS_CONFIRM, E_NO_API_KEY, Result)
from adhyaksh.safety import policy
from adhyaksh.tools import apps, files, office, system

MAX_MESSAGE = 2000
OS_INTENTS = {
    "file_create", "file_read", "file_update", "file_delete", "file_search",
    "folder_create", "office_create", "app_open", "app_close",
    "special_folder_open", "web_open", "screenshot", "system_status",
}
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


def _correct_file_folder(intent: str, slots: dict, text: str) -> tuple[str, dict]:
    """Decide file vs folder from folder-words in the text before trusting the intent."""
    slots = dict(slots)
    if _FOLDER_WORD.search(text):
        if intent == "file_create":
            intent = "folder_create"
            if "file" in slots and not slots.get("folder"):
                slots["folder"] = slots.pop("file")
    return intent, slots


def _model_slots(intent: str, text: str) -> dict:
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
    if intent == "set_identity":
        name, conf = identity.extract_name(text)
        return {"name": name, "conf": conf} if name else {}
    return {}


def _agent_dispatch(text: str, ctx: context.Context, convo_id: int, lang: str) -> _Reply:
    """Run the agent loop and turn its result into a reply."""
    res = agent_runner.run(text, convo_id, lang)
    if res.get("disabled"):
        return _Reply(res.get("reason", "Agent unavailable."), "unknown", 0.0)
    confirmation = res.get("confirmation")
    if confirmation:
        ctx.pending_agent_confirm = {
            "token": confirmation["token"],
            "action": confirmation["action"],
            "target": confirmation["target"],
            "text": text,
        }
        return _Reply("Confirm " + confirmation["action"] + " on " + confirmation["target"] +
                      "? Confirm or cancel.", "agent_confirm", action="agent_confirm",
                      confirmation=confirmation)
    ctx.agent_steps = res.get("steps", [])
    reply = res.get("reply") or "I could not complete that."
    return _Reply(reply, "agent", 1.0)


def _finish_agent_confirmation(ctx: context.Context, accept: bool,
                               convo_id: int, lang: str) -> _Reply:
    p, ctx.pending_agent_confirm = ctx.pending_agent_confirm, None
    if not accept:
        policy.cancel_guarded(p["token"])
        return _Reply(_t("cancelled", lang), "agent_confirm", action="cancel")
    res = agent_runner.resume(p["text"], convo_id, p["token"], lang)
    if res.get("disabled"):
        return _Reply(res.get("reason", "Agent unavailable."), "unknown", 0.0)
    ctx.agent_steps = res.get("steps", [])
    reply = res.get("reply") or "Done."
    return _Reply(reply, "agent", 1.0)


def _error_reply(res: Result, lang: str) -> str:
    return _t("error", lang, reason=res.message.rstrip(".") or "unknown error")


_CAPABILITIES = ("I can create, read, update, delete and search files; create Excel and Word files; "
                 "open and close allowed applications; take screenshots; check system status; "
                 "remember facts; and answer questions from your documents or the web.")


def _cannot_do_yet(lang: str) -> str:
    return _t("cannot_do_yet", lang, capabilities=_CAPABILITIES)


class _Reply:
    def __init__(self, text: str, intent: str, conf: float = 1.0, action: str = "", confirmation: dict | None = None,
                 sources: list | None = None, suggest_mode: str | None = None):
        self.text, self.intent, self.conf, self.action = text, intent, conf, action
        self.confirmation, self.sources, self.suggest_mode = confirmation, sources or [], suggest_mode


def _confirm_reply(res: Result, lang: str, ctx: context.Context, retry, intent: str, shown: str) -> _Reply:
    d = res.data
    ctx.pending_confirm = {"token": d["token"], "action": d["action"], "target": d["target"], "retry": retry}
    text = (_t("confirm_delete", lang, file=shown) if d["action"] == "file_delete"
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
        return _Reply(res.data, intent, action="llm")
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
    r"\b(?:explain|describe|define|write|compose|translate|summari[sz]e|suggest|recommend|tips?|ideas?|advice|"
    r"difference\s+between|meaning\s+of|compare|why|how|who|whom|whose|which|when|where|what|"
    r"samjh?ao|samjavo|samjha|kyun|kyu|kaise|kisne|kaun|kab|kahan|kitna|kitni|kitne|kem|kevi|kevo|koe|kone|kyare|"
    r"ketlo|ketli|ketlu|shu|kon|jaankari|jankari|vishe|baare\s+mein)\b"
    r"|समझाओ|समझाइए|क्यों|कैसे|कौन|किसने|कब|कहाँ|कितना|कितनी|कितने|क्या\s+होता|के\s+बारे\s+में|"
    r"સમજાવો|કેમ|કેવી|કોણ|ક્યારે|ક્યાં|કેટલો|કેટલી|કેટલું|વિશે", re.IGNORECASE)

# Lexical evidence that a tool-style intent really was asked for. Without any, a question is general knowledge.
_INTENT_SIGNAL = {
    "system_status": re.compile(r"cpu|ram\b|disk|storage|memory|battery|processor|laptop|computer|\bpc\b|system|"
                                r"सीपीयू|रैम|डिस्क|सिस्टम|લેપટોપ|સિસ્ટમ|રેમ|ડિસ્ક|सीपीयू|मेमोरी|મેમરી", re.IGNORECASE),
    "time_date": re.compile(r"\btime\b|\bdate\b|\bday\b|clock|baje|baja|vagya|vaage|tarikh|tareekh|din\b|vaar|"
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
    "app_open": re.compile(r"\bopen\b|launch|\bstart\b|\brun\b|kholo|khol\b|chalu|shuru|खोल|चालू|शुरू|ખોલ|ચાલુ|શરૂ",
                           re.IGNORECASE),
    "app_close": re.compile(r"close|quit|exit|kill|stop|band|bandh|off\b|बंद|બંધ", re.IGNORECASE),
    "out_of_scope": re.compile(r"$^"),
    "unknown": re.compile(r"$^"),
}


def _is_general_question(text: str) -> bool:
    """A question or request for knowledge or writing, not a tool."""
    if _TOOLISH.search(text) or _UNSUPPORTED_ACTION.search(text):
        return False
    return _is_question(text) or bool(_GENERAL_CUES.search(text))


def _general_override(text: str, intent: str) -> bool:
    """True when the model picked a tool-style or catch-all intent that nothing in the text supports,
    while the text reads as a general knowledge request. Intents with concrete tool evidence keep priority."""
    sig = _INTENT_SIGNAL.get(intent)
    return sig is not None and _is_general_question(text) and not sig.search(text)


def _dispatch(intent: str, text: str, slots: dict, ctx: context.Context, convo_id: int, lang: str,
              mode: str = "cowork") -> _Reply:
    c = _ctx_for(text, intent)
    if mode == "chat" and intent in OS_INTENTS:
        return _Reply(_t("needs_cowork", lang), intent, action="needs_cowork", suggest_mode="cowork")
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
        res = store.save_fact(text)
        if not res.ok:
            return _Reply(_error_reply(res, lang), intent)
        key = "memory_exists" if res.data["duplicate"] else "memory_saved"
        return _Reply(_t(key, lang, fact=res.data["fact"]), intent, action="memory")
    if intent == "memory_recall":
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
    if ctx.pending_agent_confirm and low in YES | NO:
        return _finish_agent_confirmation(ctx, low in YES, convo_id, lang)
    if ctx.pending_confirm and low in YES | NO:
        return _finish_confirmation(ctx, low in YES, lang)
    if ctx.pending_name and low in YES | NO:
        name, ctx.pending_name = ctx.pending_name, None
        if low in YES:
            identity.save_name(name)
            return _Reply(_t("identity_saved", lang, name=name), "set_identity", action="profile")
        return _Reply(_t("cancelled", lang), "set_identity")
    # Explicit agent invocation: "agent: <request>"
    if low.startswith("agent:"):
        return _agent_dispatch(low[len("agent:"):].strip(), ctx, convo_id, lang)
    ctx.pending_confirm = None
    ctx.pending_agent_confirm = None
    ctx.pending_name = None
    ctx.agent_steps = None
    if ctx.pending_slot:
        p, ctx.pending_slot = ctx.pending_slot, None
        if low in NO:
            return _Reply(_t("cancelled", lang), p["intent"])
        slots = dict(p["slots"])
        if p["need"] == "file":
            slots["file"] = router.find_file(text) or text.strip().split()[0]
        elif p["need"] == "app":
            slots["app"] = router.find_app(text) or text.strip()
        elif p["need"] == "folder":
            slots["folder"] = text.strip()
        elif p["need"] == "url":
            slots["url"] = router.extract_web_url(text)
        else:
            slots["content"] = text.strip()
        return _dispatch(p["intent"], text, slots, ctx, convo_id, lang, mode=mode)
    rule = router.understand(text)
    if rule:
        intent, slots = _correct_file_folder(rule.intent, rule.slots, text)
        return _dispatch(intent, text, slots, ctx, convo_id, lang, mode=mode)
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
    if conf < threshold or gap < registry.MIN_GAP:
        # Low confidence or ambiguous (small gap between the top two intents): do not dispatch
        # to the nearest intent. A plain question goes to the general answerer; other requests use
        # the agent when enabled, else the knowledge answerer.
        if llm.available() and _is_general_question(text):
            r = _llm_answer(text, convo_id, lang, "knowledge_question")
            r.conf = conf
            return r
        if agent_enabled:
            return _agent_dispatch(text, ctx, convo_id, lang)
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
        return _agent_dispatch(text, ctx, convo_id, lang)
    # Model path: extract slots using the same extractors as the rule layer.
    intent, slots = _correct_file_folder(intent, _model_slots(intent, text), text)
    r = _dispatch(intent, text, slots, ctx, convo_id, lang, mode=mode)
    r.conf = conf
    return r


def _ingest_attachments(attachments: list[tuple[str, bytes]]) -> tuple[list[str], list[str]]:
    """Index attached files. Returns (ok lines, failure lines)."""
    from adhyaksh.rag import loader
    ok, bad = [], []
    for name, data in attachments:
        res = loader.ingest_bytes(name, data)
        if res.ok:
            ok.append(f"{res.data['filename']} ({res.data['chunks']} passages)")
        else:
            bad.append(f"{name}: {res.message.rstrip('.')}")
    return ok, bad


def _attachment_reply(text: str, ok: list[str], bad: list[str], ctx: context.Context,
                      convo_id: int, lang: str, mode: str) -> _Reply:
    note = ""
    if ok:
        note += "Indexed: " + ", ".join(ok) + ".\n"
    if bad:
        note += "Could not index: " + "; ".join(bad) + ".\n"
    if not text:
        return _Reply(note.strip() + (" Ask me anything about it." if ok else ""), "attachment", action="attach")
    if ok:
        res = answerer.answer(text)
        if res.data.get("found"):
            return _Reply(note + "\n" + res.data["answer"], "doc_question", action="doc_answer",
                          sources=res.data["sources"])
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
    shown = text
    if attachments:
        names = ", ".join(n for n, _ in attachments)
        shown = (text + "\n" if text else "") + f"[Attached: {names}]"
    context.save_message(conversation_id, "user", shown)
    ctx = context.get(conversation_id)
    try:
        if attachments:
            ok, bad = _ingest_attachments(attachments)
            r = _attachment_reply(text, ok, bad, ctx, conversation_id, lang, mode)
        else:
            r = _process(text, ctx, conversation_id, lang, mode=mode)
    except Exception as exc:  # never raise to the UI for expected failures
        r = _Reply(_t("error", lang, reason=f"internal error ({type(exc).__name__})"), "error", 0.0)
    ms = (time.perf_counter() - t0) * 1000
    context.save_message(conversation_id, "assistant", r.text, r.intent, r.conf, ms)
    result = {"reply": r.text, "intent": r.intent, "confidence": round(r.conf, 3), "action": r.action,
              "latency_ms": round(ms, 1), "confirmation": r.confirmation, "sources": r.sources,
              "lang": lang, "voice": voice, "mode": mode}
    if r.suggest_mode is not None:
        result["suggest_mode"] = r.suggest_mode
    return Result.success(result)

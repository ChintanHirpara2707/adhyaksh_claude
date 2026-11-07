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
_HI_QW = {"क्या","कौन","कहाँ","कैसे","क्यों","किस","कौनसा","कितना","कितनी"}
_GU_QW = {"શું","કોણ","ક્યાં","કેવી","કેમ","શું","કયો","કયા","કેટલું","કેટલી"}
_DATE_WORDS = re.compile(r"\b(date|today|tarikh|तारीख|તારીખ)\b", re.IGNORECASE)


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


class _Reply:
    def __init__(self, text: str, intent: str, conf: float = 1.0, action: str = "", confirmation: dict | None = None,
                 sources: list | None = None):
        self.text, self.intent, self.conf, self.action = text, intent, conf, action
        self.confirmation, self.sources = confirmation, sources or []


def _confirm_reply(res: Result, lang: str, ctx: context.Context, retry, intent: str, shown: str) -> _Reply:
    d = res.data
    ctx.pending_confirm = {"token": d["token"], "action": d["action"], "target": d["target"], "retry": retry}
    text = (_t("confirm_delete", lang, file=shown) if d["action"] == "file_delete"
            else f"Confirm {d['action'].replace('_', ' ')} on {shown}? Confirm or cancel.")
    return _Reply(text, intent, action=d["action"], confirmation={"token": d["token"], "action": d["action"], "target": d["target"]})


def _need(ctx: context.Context, intent: str, need: str, slots: dict, question: str, lang: str) -> _Reply:
    ctx.pending_slot = {"intent": intent, "need": need, "slots": slots}
    return _Reply(question, intent, action="clarify")


def _llm_answer(text: str, convo_id: int, lang: str, intent: str) -> _Reply:
    if not config.get_bool("cloud_consent"):
        return _Reply(_t("llm_blocked", lang, link=llm.search_link(text)), intent)
    turns = context.history(convo_id)
    prompt = "Answer briefly and factually.\n" + "\n".join(f"{m['role']}: {m['content']}" for m in turns[-8:-1]) + f"\nuser: {text}"
    res = llm.ask(prompt)
    if res.ok:
        return _Reply(res.data, intent, action="llm")
    if res.error_code == E_NO_API_KEY:
        return _Reply(_t("llm_unavailable", lang, link=llm.search_link(text)), intent)
    return _Reply(_t("error", lang, reason=res.message.rstrip(".")) + " " + llm.search_link(text), intent)


def _dispatch(intent: str, text: str, slots: dict, ctx: context.Context, convo_id: int, lang: str) -> _Reply:
    c = _ctx_for(text, intent)
    if intent == "greet":
        return _Reply(_t("greet", lang), intent)
    if intent == "bot_identity":
        return _Reply("I am ADHYAKSH.", "bot_identity")
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
        if not _is_question(text):
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
            return _Reply("I could not tell which website to open.", "web_open")
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
    return _Reply(_t("unknown", lang), "unknown")


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


def _process(text: str, ctx: context.Context, convo_id: int, lang: str) -> _Reply:
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
        else:
            slots["content"] = text.strip()
        return _dispatch(p["intent"], text, slots, ctx, convo_id, lang)
    rule = router.match_rules(text)
    if rule:
        return _dispatch(rule.intent, text, rule.slots, ctx, convo_id, lang)
    intent, conf, gap = registry.predict(text)
    if intent == "unknown" and conf == 0.0 and not registry.available():
        return _Reply("No trained model is active. Run: python -m adhyaksh.nlu.train --all", "unknown", 0.0)
    threshold = config.get_float("confidence_threshold")
    agent_enabled = llm.get_provider() is not None and config.get_bool("cloud_consent")
    if conf < threshold or gap < registry.MIN_GAP:
        # Low confidence or ambiguous (small gap between the top two intents): do not dispatch
        # to the nearest intent. Use the agent when enabled, else the knowledge answerer.
        if agent_enabled:
            return _agent_dispatch(text, ctx, convo_id, lang)
        if llm.get_provider() is not None and config.get_bool("cloud_consent"):
            r = _llm_answer(text, convo_id, lang, "knowledge_question")
            r.conf = conf
            return r
        r = _Reply(_t("unknown", lang), "unknown", conf, action="low_confidence")
        return r
    if _looks_multi_step(text) and agent_enabled:
        return _agent_dispatch(text, ctx, convo_id, lang)
    r = _dispatch(intent, text, {}, ctx, convo_id, lang)
    r.conf = conf
    return r


def handle_message(text: str, conversation_id: int, voice: bool = False) -> Result:
    """Process one user message and return reply, intent, confidence, action, timing."""
    t0 = time.perf_counter()
    text = (text or "").strip()[:MAX_MESSAGE]
    if not text:
        return Result.failure(E_LOW_CONFIDENCE, "Empty message.")
    lang = detect_lang(text)
    context.save_message(conversation_id, "user", text)
    ctx = context.get(conversation_id)
    try:
        r = _process(text, ctx, conversation_id, lang)
    except Exception as exc:  # never raise to the UI for expected failures
        r = _Reply(_t("error", lang, reason=f"internal error ({type(exc).__name__})"), "error", 0.0)
    ms = (time.perf_counter() - t0) * 1000
    context.save_message(conversation_id, "assistant", r.text, r.intent, r.conf, ms)
    return Result.success({"reply": r.text, "intent": r.intent, "confidence": round(r.conf, 3), "action": r.action,
                           "latency_ms": round(ms, 1), "confirmation": r.confirmation, "sources": r.sources,
                           "lang": lang, "voice": voice})

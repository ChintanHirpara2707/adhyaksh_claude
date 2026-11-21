"""Service layer for the Chat page: the only adhyaksh functions that page may call.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

from adhyaksh import config, db
from adhyaksh.chat import context, engine, identity
from adhyaksh.nlu import dataset
from adhyaksh.rag import loader, retriever, sources
from adhyaksh.voice import bridge, speech, stt

# adhyaksh.voice.bridge
bridge_handle_audio = bridge.handle_audio
bridge_voice_input = bridge.voice_input

# adhyaksh.config
get = config.get
get_bool = config.get_bool
set_value = config.set_value

# adhyaksh.chat.context
context_get = context.get
context_history = context.history
context_latest_conversation = context.latest_conversation
context_new_conversation = context.new_conversation

# adhyaksh.nlu.dataset
INTENTS = dataset.INTENTS

# Example prompts for an empty conversation: (label with a Material icon, prompt). Each one works offline.
SUGGESTIONS = {
    "cowork": [
        (":material/note_add: Create notes.txt", "create notes.txt with buy milk"),
        (":material/memory: What uses the most memory?", "which apps use the most RAM"),
        (":material/alarm: Remind me in 20 minutes", "remind me in 20 minutes to stretch"),
        (":material/monitor_heart: System status", "show system status"),
    ],
    "chat": [
        (":material/calculate: What is 15% of 2400?", "what is 15% of 2400"),
        (":material/bookmark_add: Remember my car", "remember that my car is Audi"),
        (":material/schedule: What time is it?", "what time is it"),
        (":material/help: What can you do?", "what can you do"),
    ],
}


def greeting(name: str | None, hour: int | None = None) -> str:
    """'Good morning, Priya' by local time of day (5-12 morning, 12-17 afternoon, else evening)."""
    import datetime
    h = datetime.datetime.now().hour if hour is None else hour
    part = "morning" if 5 <= h < 12 else "afternoon" if 12 <= h < 17 else "evening"
    return f"Good {part}, {name}" if name else f"Good {part}"

# adhyaksh.chat.engine, or the background engine when it is running (adhyaksh.client): one conversation state for the
# console, the HUD and voice. Attachments are always handled here (the files are in this process).
def engine_handle_message(text, conversation_id, voice=False, mode="cowork", attachments=None, stream=False):
    """stream=True: a general question may come back as data["stream"] (pieces to show as they arrive). Through the
    background engine replies always arrive whole (the HTTP API is not streamed)."""
    from adhyaksh import client
    if not attachments and client.available():
        res = client.message(text, conversation_id, voice=voice, mode=mode)
        if res.ok or res.error_code != "E_NETWORK":
            return res
    return engine.handle_message(text, conversation_id, voice=voice, mode=mode, attachments=attachments, stream=stream)


def engine_confirm(conversation_id, accept):
    from adhyaksh import client
    if client.available():
        res = client.confirm(conversation_id, accept)
        if res.ok or res.error_code != "E_NETWORK":
            return res
    return engine.confirm(conversation_id, accept)


def pending_confirm(conversation_id):
    """The confirmation the conversation waits for ({token, action, target}) or None, wherever it is held."""
    from adhyaksh import client
    if client.available():
        return client.pending(conversation_id)
    p = context.get(conversation_id).pending_confirm
    return {k: p.get(k) for k in ("token", "action", "target")} if p else None

# adhyaksh.chat.identity
identity_get_name = identity.get_name

# adhyaksh.rag.loader
loader_delete_document = loader.delete_document
loader_list_documents = loader.list_documents

# adhyaksh.rag.retriever
retriever_embedding_mode = retriever.embedding_mode

# adhyaksh.rag.sources
sources_active = sources.active
sources_count = sources.count
sources_create_notebook = sources.create_notebook
sources_list_notebooks = sources.list_notebooks
sources_set_active = sources.set_active

# adhyaksh.voice.speech
speech_clean_transcript = speech.clean_transcript
speech_confirm_prompt = speech.confirm_prompt

# adhyaksh.voice.stt
stt_available = stt.available
stt_transcribe = stt.transcribe


def save_intent_correction(message_id: int, correct_intent: str, note: str = "") -> None:
    """Store the user's correction of a misread message (used as training feedback)."""
    db.execute("INSERT INTO feedback(message_id, correct_intent, note, created_at) VALUES(?,?,?,?)",
               (message_id, correct_intent, note, db.utcnow()))


# ---- conversations (Chat sidebar) -------------------------------------------------------------------------------------
DEFAULT_TITLE = "Chat"  # the title every new conversation gets; shown as its first message until renamed
TITLE_CHARS = 48


def _title(row: dict) -> str:
    stored = (row.get("title") or "").strip()
    if stored and stored != DEFAULT_TITLE:
        return stored
    first = " ".join((row.get("first") or "").split())
    if not first:
        return "New chat"
    return first if len(first) <= TITLE_CHARS else first[:TITLE_CHARS - 1].rstrip() + "..."


def conversations_list(query: str = "", limit: int = 50, keep: int | None = None) -> list[dict]:
    """Conversations with at least one message (plus `keep`, the open one), most recently used first:
    [{"id", "title", "updated_at", "count"}]. `query` matches the title or any message, ignoring case."""
    q = " ".join((query or "").split())[:100]
    like = "%" + q.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"  # '!' escapes LIKE wildcards
    rows = db.query_all(
        "SELECT c.id, c.title, c.created_at,"
        " COALESCE(MAX(m.created_at), c.created_at) AS updated_at, COUNT(m.id) AS count,"
        " (SELECT content FROM messages f WHERE f.conversation_id = c.id AND f.role = 'user' ORDER BY f.id LIMIT 1) AS first"
        " FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id"
        " GROUP BY c.id"
        " HAVING (COUNT(m.id) > 0 OR c.id = ?)"
        "  AND (? = '' OR c.title LIKE ? ESCAPE '!' OR EXISTS (SELECT 1 FROM messages s WHERE s.conversation_id = c.id"
        "       AND s.content LIKE ? ESCAPE '!'))"
        # newest activity first (message ids grow; timestamps share seconds); an empty open chat on top
        " ORDER BY COUNT(m.id) = 0 DESC, MAX(m.id) DESC, c.id DESC LIMIT ?",
        (int(keep or 0), q, like, like, int(limit)))
    # A title made from the first message is matched through the message search above.
    return [{"id": r["id"], "title": _title(r), "updated_at": r["updated_at"], "count": r["count"]} for r in rows]


def conversation_title(conversation_id: int) -> str:
    row = db.query_one("SELECT c.title, (SELECT content FROM messages f WHERE f.conversation_id = c.id AND f.role = 'user'"
                       " ORDER BY f.id LIMIT 1) AS first FROM conversations c WHERE c.id = ?", (int(conversation_id),))
    return _title(row) if row else "New chat"


def conversation_rename(conversation_id: int, title: str) -> bool:
    """Rename a conversation. An empty title is refused; long titles are cut to 60 characters."""
    title = " ".join((title or "").split())[:60]
    if not title:
        return False
    db.execute("UPDATE conversations SET title = ? WHERE id = ?", (title, int(conversation_id)))
    return True


def conversation_delete(conversation_id: int) -> None:
    """Delete a conversation, its messages (cascade) and its saved confirmation replays. Cannot be undone."""
    cid = int(conversation_id)
    db.execute("DELETE FROM confirm_replays WHERE conversation_id = ?", (cid,))
    db.execute("DELETE FROM conversations WHERE id = ?", (cid,))
    context._CTX.pop(cid, None)


def conversation_new(current: int | None = None) -> int:
    """A new chat; reuses `current` when it is still empty, so repeated clicks do not pile up empty chats."""
    if current and not db.query_one("SELECT 1 FROM messages WHERE conversation_id = ? LIMIT 1", (int(current),)) \
            and db.query_one("SELECT 1 FROM conversations WHERE id = ?", (int(current),)):
        return int(current)
    return context.new_conversation()


def conversation_exists(conversation_id: int) -> bool:
    return db.query_one("SELECT 1 FROM conversations WHERE id = ?", (int(conversation_id),)) is not None


# ---- the current chat, for the life of the server process ------------------------------------------------------------
# Kept in st.cache_resource (one per `streamlit run`), not in st.session_state (one per browser page): pressing F5 or
# reopening the tab keeps the same chat, while starting the server again opens a fresh, empty New chat. The
# conversation row is created only when the first message is sent, so empty chats are never stored.
def _max_message_id() -> int:
    row = db.query_one("SELECT COALESCE(MAX(id), 0) AS n FROM messages")
    return int(row["n"]) if row else 0


def _new_process_store() -> dict:
    return {"cid": None, "since": _max_message_id()}


def _store() -> dict:
    return _process_store()


try:
    import streamlit as _st
    _process_store = _st.cache_resource(show_spinner=False)(_new_process_store)
except Exception:  # pragma: no cover - streamlit is always installed with the console
    _PROCESS: dict = {}

    def _process_store() -> dict:
        return _PROCESS.setdefault("store", _new_process_store())


def reset_process_store() -> None:
    """Forget the current chat and the run start, as a new server process would (tests)."""
    if hasattr(_process_store, "clear"):
        _process_store.clear()
    else:  # pragma: no cover
        _PROCESS.clear()


def current_chat() -> int | None:
    """The chat open in this server run, or None for a new chat whose row does not exist yet."""
    s = _store()
    if s["cid"] is not None and not conversation_exists(s["cid"]):
        s["cid"] = None  # deleted (here or elsewhere): back to a new chat
    return s["cid"]


def set_current_chat(conversation_id: int | None) -> None:
    _store()["cid"] = int(conversation_id) if conversation_id else None


def ensure_chat() -> int:
    """The current chat's id, creating its row now (on the first message of a new chat)."""
    cid = current_chat()
    if cid is None:
        cid = context.new_conversation()
        set_current_chat(cid)
    return cid


def run_started_after() -> int:
    """The newest message id that existed when this server run started (later ids belong to this run)."""
    return int(_store()["since"])


# ---- message actions: tool steps, regenerate, edit and resend -----------------------------------------------------------
def _step(row: dict) -> dict:
    from adhyaksh.services import activity
    out = activity.outcome(row.get("result", ""))
    return {"action": (row.get("action") or "").replace("_", " "), "target": row.get("target") or "",
            "outcome": out, "result": row.get("result") or "", "level": activity.LEVELS.get(row.get("level"), ""),
            "confirmed": row.get("confirmed") or "none", "ts": row.get("ts") or "",
            "state": "complete" if out in ("done", "cancelled") else "error"}


def turn_steps(messages: list[dict]) -> dict[int, list[dict]]:
    """Which tools ran for each reply: {assistant message id: [step]} from the append-only audit log (every tool
    action passes the safety gateway, which writes one row). A row belongs to the first reply written at or after it,
    within that turn (from the user's message to the reply). Read only; the engine is not involved."""
    msgs = [m for m in messages if m.get("created_at")]
    if not any(m["role"] == "assistant" for m in msgs):
        return {}
    rows = db.query_all("SELECT * FROM audit_log WHERE ts >= ? AND ts <= ? ORDER BY id",
                        (msgs[0]["created_at"], msgs[-1]["created_at"]))
    out: dict[int, list[dict]] = {}

    def norm(s: str) -> str:
        return " ".join((s or "").casefold().split())

    for r in rows:
        said = norm(r.get("user_text"))
        start, asked = None, []  # the turn's start, and what the user said in this conversation so far
        for m in msgs:
            if m["role"] == "user":
                start = m["created_at"]
                asked.append(norm(m["content"]))
            elif start is not None and start <= r["ts"] <= m["created_at"]:
                # The tool records the request it served (one step of a multi-step message; the original request
                # after a typed "yes"), so a row from another conversation in the same second is left out.
                # Turns within one second share a window, so a turn whose words do not match is passed over.
                if not said or said == norm(r.get("action")) or any(said in a or a in said for a in asked if a):
                    out.setdefault(m["id"], []).append(_step(r))
                    break
    return out


def _last_turn(conversation_id: int) -> tuple[dict | None, dict | None, list[dict]]:
    """(last user message, the reply after it or None, recent history)."""
    hist = context.history(int(conversation_id), 50)
    user = next((m for m in reversed(hist) if m["role"] == "user"), None)
    reply = None
    if user is not None:
        reply = next((m for m in hist if m["id"] > user["id"] and m["role"] == "assistant"), None)
    return user, reply, hist


def can_regenerate(conversation_id: int) -> bool:
    """Only the last reply, only when nothing is waiting for confirmation and no tool ran in that turn (asking
    again must never repeat an action)."""
    user, reply, hist = _last_turn(conversation_id)
    if user is None or reply is None or pending_confirm(conversation_id):
        return False
    return reply["id"] not in turn_steps(hist)


def _drop_from(conversation_id: int, message_id: int) -> None:
    db.execute("DELETE FROM messages WHERE conversation_id = ? AND id >= ?", (int(conversation_id), int(message_id)))


def regenerate(conversation_id: int, mode: str = "cowork"):
    """Ask the last question again for a new answer (the old turn is replaced; the model's cache is skipped).
    Runs in this process so a streamed answer can be shown; returns what engine_handle_message returns."""
    from adhyaksh.result import E_BLOCKED, Result
    if not can_regenerate(conversation_id):
        return Result.failure(E_BLOCKED, "This reply cannot be regenerated: a tool ran or it is not the last reply.")
    user, _, _ = _last_turn(conversation_id)
    _drop_from(conversation_id, user["id"])
    from adhyaksh.llm import base as llm
    with llm.fresh():
        return engine.handle_message(user["content"], int(conversation_id), mode=mode, stream=True)


def edit_and_resend(conversation_id: int, message_id: int, text: str, mode: str = "cowork"):
    """Send an edited version of the last user message. If no tool ran in that turn the old turn is replaced;
    if one did, it stays in the history (it really happened) and the edit is sent as a new message."""
    from adhyaksh.result import E_BAD_ARGUMENTS, Result
    text = (text or "").strip()
    user, reply, hist = _last_turn(conversation_id)
    if not text or user is None or user["id"] != int(message_id):
        return Result.failure(E_BAD_ARGUMENTS, "Only the last message can be edited, and it cannot be empty.")
    ran_tool = reply is not None and reply["id"] in turn_steps(hist)
    if not ran_tool and not pending_confirm(conversation_id):
        _drop_from(conversation_id, user["id"])
    return engine_handle_message(text, int(conversation_id), mode=mode, stream=True)

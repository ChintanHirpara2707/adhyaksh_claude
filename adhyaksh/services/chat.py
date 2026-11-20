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

# adhyaksh.chat.engine, or the background engine when it is running (adhyaksh.client): one conversation state for the
# console, the HUD and voice. Attachments are always handled here (the files are in this process).
def engine_handle_message(text, conversation_id, voice=False, mode="cowork", attachments=None):
    from adhyaksh import client
    if not attachments and client.available():
        res = client.message(text, conversation_id, voice=voice, mode=mode)
        if res.ok or res.error_code != "E_NETWORK":
            return res
    return engine.handle_message(text, conversation_id, voice=voice, mode=mode, attachments=attachments)


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

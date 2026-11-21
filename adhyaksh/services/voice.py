"""Service layer for the Voice page: the only adhyaksh functions that page may call.

Two ways to talk:
* the background engine's native voice (wake word, local speech model) when it runs: the page shows its live state
  and offers push-to-talk and stop-speaking;
* otherwise the browser microphone component in the page itself, as in Chat.
Either way every request goes through the same engine and safety gateway as typing.
"""
from __future__ import annotations

from adhyaksh import client, config, events
from adhyaksh.chat import context, identity
from adhyaksh.services import chat as chat_svc
from adhyaksh.voice import bridge, speech, stt

STATES = events.STATES


def engine_running() -> bool:
    return client.available()


def engine_voice() -> dict:
    """{"running": bool, ...} of the engine's native voice (False when the engine is not running)."""
    return client.voice_status() if client.available() else {"running": False}


def state() -> dict:
    """{"state", "detail"}: state is idle, listening, thinking, speaking or executing; from the engine when it runs,
    else from this process's event bus."""
    s = client.state() if client.available() else None
    if not s or s.get("state") not in STATES:
        s = events.current_state()
    st = s.get("state") if s.get("state") in STATES else "idle"
    return {"state": st, "detail": str(s.get("detail") or "")}


def push_to_talk():
    return client.voice_listen()


def stop_speaking_engine():
    return client.voice_quiet()


# conversation (shared with the Chat page through st.session_state["cid"])
latest_conversation = context.latest_conversation
new_conversation = context.new_conversation
history = context.history
current_chat = chat_svc.current_chat  # the chat open in this server run (shared with the Chat page)
ensure_chat = chat_svc.ensure_chat
identity_get_name = identity.get_name
handle_message = chat_svc.engine_handle_message
confirm = chat_svc.engine_confirm
pending_confirm = chat_svc.pending_confirm

# voice building blocks
get = config.get
get_bool = config.get_bool
set_value = config.set_value
voice_input = bridge.voice_input
handle_audio = bridge.handle_audio
confirm_prompt = speech.confirm_prompt
stt_available = stt.available

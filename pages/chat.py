import streamlit as st
import time

from adhyaksh.services import chat as svc
from adhyaksh.ui import components as ui

ui.chat_width()


def apply_ui_hints(res) -> None:
    """Act on UI hints returned by the engine: forward a voice command, switch to a page."""
    data = res.data or {}
    cmd = data.get("voice_cmd")
    if cmd:
        st.session_state["voice_cmd"] = {**cmd, "nonce": str(time.time_ns())}
    page = data.get("open_page")
    if page:
        st.session_state["goto_page"] = page

ui.page_header("Chat", "Type or speak a command in English, Hindi, Gujarati or a mix.")
if svc.identity_get_name() is None:
    ui.first_run_form()
    st.stop()

if "cid" not in st.session_state:
    st.session_state["cid"] = svc.context_latest_conversation()
cid = st.session_state["cid"]
st.session_state.setdefault("mode", "cowork")
mode = st.session_state["mode"]
if st.button("New conversation"):
    st.session_state["cid"] = svc.context_new_conversation()
    st.rerun()

history = svc.context_history(cid, 50)
if not history:
    ui.empty_state("No messages yet. Try: create notes.txt, remember that my car is Audi, or show system status.")

# Stream the final answer of the latest agent turn, once per new message.
last_assistant = next((m for m in reversed(history) if m["role"] == "assistant"), None)
streaming = False
if last_assistant and last_assistant.get("intent") in ("agent", "knowledge_question"):
    if st.session_state.get("streamed_agent_msg_id") != last_assistant["id"]:
        streaming = True
        st.session_state["streamed_agent_msg_id"] = last_assistant["id"]

for m in history:
    with st.chat_message(m["role"]):
        if streaming and m is last_assistant:
            def _gen(text: str = m["content"]):
                for word in text.split():
                    yield word + " "
                    time.sleep(0.015)
            st.write_stream(_gen())
        else:
            st.markdown(m["content"])
        if m["role"] == "assistant":
            intent_val = m.get("intent") or "unknown"
            key_prefix = f"wrong_{m['id']}"
            if st.button("Wrong intent?", key=key_prefix):
                st.session_state[f"correcting_{m['id']}"] = True
                st.rerun()
            if st.session_state.get(f"correcting_{m['id']}"):
                st.caption(f"Detected intent: {intent_val}")
                correct = st.selectbox("Correct intent", svc.INTENTS,
                                       index=svc.INTENTS.index(intent_val)
                                       if intent_val in svc.INTENTS else 0,
                                       key=f"intent_{m['id']}")
                if st.button("Save correction", key=f"save_{m['id']}"):
                    svc.save_intent_correction(m["id"], correct)
                    st.session_state[f"correcting_{m['id']}"] = False
                    st.success("Correction saved. Retrain to use it.")
                    st.rerun()

# Show the agent steps live (collapsible), attached to the latest turn.
# ctx = svc.context_get(cid)
# steps = ctx.agent_steps or []
# if steps:
#     with st.expander("Agent steps", expanded=True):
#         for s in steps:
#             label = s.get("label") or s.get("tool") or "step"
#             target = s.get("target") or ""
#             st.markdown(f"**{label}** — {target or '—'}")
#             status = s.get("status", "")
#             if status == "ok":
#                 st.success("done")
#             elif status == "confirm":
#                 st.info("awaiting confirmation")
#             elif status == "error":
#                 st.error("error")
#             else:
#                 st.caption("running…")
#             result = s.get("result", "")
#             if result:
#                 st.code(result)

_nbs = svc.sources_list_notebooks()
_active = svc.sources_active()
with st.expander(f"Notebook: {_active['name']} ({svc.sources_count()} sources)"):
    _names = [n["name"] for n in _nbs]
    _pick = st.selectbox("Active notebook", _names, index=_names.index(_active["name"]) if _active["name"] in _names else 0,
                         help="Attachments go into the active notebook, and document questions are answered from it only.")
    if _pick != _active["name"]:
        svc.sources_set_active(next(n["id"] for n in _nbs if n["name"] == _pick))
        st.rerun()
    _n1, _n2 = st.columns([4, 1])
    _new = _n1.text_input("New notebook name", max_chars=60, label_visibility="collapsed", placeholder="New notebook name")
    if _n2.button("Create") and _new.strip():
        svc.sources_create_notebook(_new)
        st.rerun()
    _docs = svc.loader_list_documents(_active["id"])
    if not _docs:
        st.caption("No sources yet. Use the paperclip in the message box to attach a PDF, DOCX or text file.")
    for _d in _docs:
        _c1, _c2 = st.columns([5, 1])
        _c1.markdown(f"**{_d['filename']}** - {_d['chunks']} passages")
        if _d.get("summary"):
            _c1.caption(_d["summary"][:280])
        if _c2.button("Remove", key=f"rmdoc_{_d['id']}"):
            svc.loader_delete_document(int(_d["id"]))
            st.rerun()
    st.caption("Search method: " + {"local": "local embeddings (multilingual)", "gemini": "Gemini embeddings (cloud)",
                                    "tfidf": "TF-IDF keywords (offline)"}[svc.retriever_embedding_mode()])

pending = svc.pending_confirm(cid)  # here or in the background engine, wherever the conversation runs
if pending:
    choice = ui.confirmation_card(pending["action"].replace("_", " "), pending["target"], key=f"c_{pending['token']}")
    if choice:
        svc.engine_confirm(cid, choice == "confirm")
        st.rerun()

last = next((m for m in reversed(history) if m["role"] == "assistant"), None)
last_id = last["id"] if last else 0
st.session_state.setdefault("seen_assistant", last_id)
# Replies are spoken when "Speak replies aloud" is on, or when the reply answers a spoken command.
new_reply = last is not None and last_id != st.session_state["seen_assistant"]
speak = new_reply and (svc.get_bool("voice_reply") or st.session_state.pop("voice_reply_pending", False))
vcmd = st.session_state.get("voice_cmd") or {}
_speak_text = last["content"] if speak else ""
if speak and (last.get("intent") == "agent_confirm" or "Confirm or cancel" in _speak_text) and "say yes" not in _speak_text.lower():
    # Spoken confirmation: the question is read out and answered with a spoken yes or no.
    _speak_text = _speak_text.replace("Confirm or cancel.", "").strip() + " " + svc.speech_confirm_prompt(svc.get("voice_lang"))
heard = svc.bridge_voice_input(theme_name=svc.get("theme") or "light", lang=svc.get("voice_lang") or "en-IN",
                           speak_text=_speak_text,
                           status=st.session_state.pop("voice_status", ""),
                           speak_nonce=str(last_id) if speak else "",
                           command=vcmd or None, command_nonce=vcmd.get("nonce", ""),
                           handsfree_default=svc.get_bool("voice_handsfree"),
                           wake_default=svc.get_bool("voice_wake_word"))
if new_reply:
    st.session_state["seen_assistant"] = last_id
if heard and heard.get("nonce") != st.session_state.get("voice_nonce"):
    st.session_state["voice_nonce"] = heard["nonce"]
    svc.set_value("voice_handsfree", "true" if heard.get("handsfree") else "false")
    svc.set_value("voice_wake_word", "true" if heard.get("wake") else "false")
    if not heard.get("setting") and heard.get("audio_b64"):
        with st.spinner("Transcribing on this laptop"):
            _out = svc.bridge_handle_audio(heard["audio_b64"], heard.get("lang", "en-IN"), bool(heard.get("handsfree")), bool(heard.get("wake")))
        if _out.get("text"):
            heard["text"] = _out["text"]
        elif _out.get("error"):
            st.session_state["voice_status"] = _out["error"]
            st.rerun()
        else:
            st.session_state["voice_status"] = "Waiting for the wake word 'Adhyaksh'" if _out.get("ignore") == "no wake word" else "Yes? I am listening"
            st.rerun()
    if not heard.get("setting") and heard.get("text"):
        st.caption(f"Heard: {heard['text']}")
        st.session_state["suggest_switch"] = False
        with st.spinner("Working"):
            result = svc.engine_handle_message(heard["text"], cid, voice=True, mode=mode)
        st.session_state["voice_reply_pending"] = True
        apply_ui_hints(result)
        if result.data and result.data.get("suggest_mode") == "cowork":
            st.session_state["suggest_switch"] = True
        st.rerun()

# Mode toggle: small control directly above the chat input.
st.divider()
if mode == "chat" and st.session_state.get("suggest_switch"):
    st.info("That action needs Cowork mode. Switch to Cowork to run it.")
    if st.button("Switch to Cowork", key="switch_cowork"):
        st.session_state["mode"] = "cowork"
        st.session_state["mode_toggle"] = "Cowork"
        st.session_state["suggest_switch"] = False
        st.rerun()
st.caption("Cowork: can open apps and work with your files."
           if mode == "cowork" else "Chat: answers and information only.")
chosen = st.radio("Mode", ["Chat", "Cowork"],
                  index=0 if mode == "chat" else 1,
                  horizontal=True, key="mode_toggle",
                  label_visibility="collapsed")
new_mode = chosen.lower()
if new_mode != mode:
    st.session_state["mode"] = new_mode
    st.session_state["suggest_switch"] = False
    st.rerun()

_local_stt = svc.stt_available()
prompt = st.chat_input("Type a command, or attach a document or a photo", accept_file="multiple",
                       file_type=["pdf", "docx", "txt", "md", "csv", "jpg", "jpeg", "png", "webp"],
                       accept_audio=_local_stt)
if prompt:
    text = (getattr(prompt, "text", None) if not isinstance(prompt, str) else prompt) or ""
    _audio = None if isinstance(prompt, str) else getattr(prompt, "audio", None)
    if _audio is not None and not text:
        with st.spinner("Transcribing on this laptop"):
            _tr = svc.stt_transcribe(_audio.getvalue(), svc.get("voice_lang"))
        if _tr.ok:
            text = svc.speech_clean_transcript(_tr.data["text"])
            st.session_state["voice_reply_pending"] = True
        else:
            st.session_state["voice_status"] = _tr.message
    files = [] if isinstance(prompt, str) else [(f.name, f.getvalue()) for f in (prompt.files or [])]
    st.session_state["suggest_switch"] = False
    with st.spinner("Working"):
        result = svc.engine_handle_message(text, cid, mode=mode, attachments=files)
    apply_ui_hints(result)
    if result.data and result.data.get("suggest_mode") == "cowork":
        st.session_state["suggest_switch"] = True
    st.rerun()

_goto = st.session_state.pop("goto_page", None)
if _goto in ("vision", "performance"):
    st.switch_page(f"pages/{_goto}.py")

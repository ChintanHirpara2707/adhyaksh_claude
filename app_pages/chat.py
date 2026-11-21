import time

import streamlit as st

from adhyaksh.services import chat as svc
from adhyaksh.ui import components as ui

ui.chat_width()

MODES = {"Chat": "chat", "Cowork": "cowork"}


def apply_ui_hints(res) -> None:
    """Act on UI hints returned by the engine: forward a voice command, switch to a page."""
    data = res.data or {}
    cmd = data.get("voice_cmd")
    if cmd:
        st.session_state["voice_cmd"] = {**cmd, "nonce": str(time.time_ns())}
    page = data.get("open_page")
    if page:
        st.session_state["goto_page"] = page


name = svc.identity_get_name()
if name is None:
    ui.page_header("Chat", "Type or speak a command in English, Hindi, Gujarati or a mix.")
    ui.first_run_form()
    st.stop()

if "cid" not in st.session_state:
    st.session_state["cid"] = svc.context_latest_conversation()
cid = st.session_state["cid"]
st.session_state.setdefault("mode", "cowork")
mode = st.session_state["mode"]

history = svc.context_history(cid, 50)

top = st.container(horizontal=True, horizontal_alignment="right")
if top.button("New conversation", icon=":material/add:", type="tertiary"):
    st.session_state["cid"] = svc.context_new_conversation()
    st.rerun()

# Empty conversation: a greeting and example prompts; a chosen example is sent like a typed message.
suggested = None
suggestions = st.empty()
if not history:
    with suggestions.container():
        ui.chat_welcome(svc.greeting(name), "What should we do? Type below, attach a file, or pick an example.")
        options = dict(svc.SUGGESTIONS[mode])
        picked = st.pills("Examples", list(options), label_visibility="collapsed", key=f"suggest_{cid}_{mode}")
        if picked:
            suggested = options[picked]

for m in history:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        if m["role"] == "assistant":
            intent_val = m.get("intent") or "unknown"
            if st.button("Wrong intent?", key=f"wrong_{m['id']}", type="tertiary"):
                st.session_state[f"correcting_{m['id']}"] = True
                st.rerun()
            if st.session_state.get(f"correcting_{m['id']}"):
                st.caption(f"Detected intent: {intent_val}")
                correct = st.selectbox("Correct intent", svc.INTENTS,
                                       index=svc.INTENTS.index(intent_val) if intent_val in svc.INTENTS else 0,
                                       key=f"intent_{m['id']}")
                if st.button("Save correction", key=f"save_{m['id']}"):
                    svc.save_intent_correction(m["id"], correct)
                    st.session_state[f"correcting_{m['id']}"] = False
                    st.success("Correction saved. Retrain to use it.")
                    st.rerun()

pending = svc.pending_confirm(cid)  # here or in the background engine, wherever the conversation runs
if pending:
    choice = ui.confirmation_card(pending["action"].replace("_", " "), pending["target"], key=f"c_{pending['token']}")
    if choice:
        svc.engine_confirm(cid, choice == "confirm")
        st.rerun()

live = st.container()  # the turn being answered now is drawn here, above the voice control

# Browser voice: spoken replies, hands-free and the wake word.
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
# Folded away unless hands-free or the wake word is on; it keeps speaking replies while folded.
_voice_on = svc.get_bool("voice_handsfree") or svc.get_bool("voice_wake_word")
with st.expander("Voice controls", icon=":material/settings_voice:", expanded=_voice_on):
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

if mode == "chat" and st.session_state.get("suggest_switch"):
    st.info("That action needs Cowork mode. Switch to Cowork to run it.")
    if st.button("Switch to Cowork", key="switch_cowork"):
        st.session_state["mode"] = "cowork"
        st.session_state["mode_toggle"] = "Cowork"
        st.session_state["suggest_switch"] = False
        st.rerun()

# The composer, pinned to the bottom: the message box (plus button for files, mic when the local speech model is
# ready), then one row with the mode pill, the notebook picker and the voice page.
_local_stt = svc.stt_available()
with st.bottom:
    prompt = st.chat_input("Ask anything, or tell me what to do", accept_file="multiple",
                           file_type=["pdf", "docx", "txt", "md", "csv", "jpg", "jpeg", "png", "webp"],
                           accept_audio=_local_stt, key="composer")
    bar = st.container(horizontal=True, vertical_alignment="center", gap="small")
    with bar:
        st.session_state.setdefault("mode_toggle", "Cowork" if mode == "cowork" else "Chat")
        chosen = st.segmented_control("Mode", list(MODES), required=True, key="mode_toggle",
                                      label_visibility="collapsed",
                                      help="Chat answers and explains only. Cowork can also open apps and work with your files.")
        _nbs = svc.sources_list_notebooks()
        _active = svc.sources_active()
        with st.popover(f"{_active['name']} ({svc.sources_count()})", icon=":material/menu_book:",
                        help="Notebook: attachments go here, and document questions are answered from it only."):
            _names = [n["name"] for n in _nbs]
            _pick = st.selectbox("Active notebook", _names,
                                 index=_names.index(_active["name"]) if _active["name"] in _names else 0)
            if _pick != _active["name"]:
                svc.sources_set_active(next(n["id"] for n in _nbs if n["name"] == _pick))
                st.rerun()
            _n1, _n2 = st.columns([4, 1], vertical_alignment="bottom")
            _new = _n1.text_input("New notebook", max_chars=60, placeholder="New notebook name")
            if _n2.button("Create") and _new.strip():
                svc.sources_create_notebook(_new)
                st.rerun()
            _docs = svc.loader_list_documents(_active["id"])
            if not _docs:
                st.caption("No sources yet. Use the plus button in the message box to attach a PDF, DOCX or text file.")
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
        if not _local_stt and st.button("Voice", icon=":material/mic:", type="tertiary",
                                        help="Open the Voice page to talk instead of typing."):
            st.session_state["goto_page"] = "voice"

new_mode = MODES.get(chosen, mode)
if new_mode != mode:
    st.session_state["mode"] = new_mode
    st.session_state["suggest_switch"] = False
    st.rerun()

if prompt or suggested:
    text = suggested or (getattr(prompt, "text", None) if not isinstance(prompt, str) else prompt) or ""
    _audio = None if suggested or isinstance(prompt, str) else getattr(prompt, "audio", None)
    if _audio is not None and not text:
        with st.spinner("Transcribing on this laptop"):
            _tr = svc.stt_transcribe(_audio.getvalue(), svc.get("voice_lang"))
        if _tr.ok:
            text = svc.speech_clean_transcript(_tr.data["text"])
            st.session_state["voice_reply_pending"] = True
        else:
            st.session_state["voice_status"] = _tr.message
    files = [] if suggested or isinstance(prompt, str) else [(f.name, f.getvalue()) for f in (prompt.files or [])]
    st.session_state["suggest_switch"] = False
    suggestions.empty()
    with live:
        if text:
            with st.chat_message("user"):
                st.markdown(text)
        with st.spinner("Working"):
            result = svc.engine_handle_message(text, cid, mode=mode, attachments=files, stream=not files)
        if result.ok and result.data.get("stream") is not None:
            with st.chat_message("assistant"):
                st.write_stream(result.data["stream"])  # the model's answer, word by word as it is written; saved at the end
    apply_ui_hints(result)
    if result.data and result.data.get("suggest_mode") == "cowork":
        st.session_state["suggest_switch"] = True
    st.rerun()

_goto = st.session_state.pop("goto_page", None)
if _goto in ("vision", "performance", "voice"):
    st.switch_page(f"app_pages/{_goto}.py")

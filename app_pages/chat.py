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
        if cmd.get("action") in ("start", "wake_on"):
            st.session_state["goto_page"] = "voice"  # listening happens on the Voice page
    page = data.get("open_page")
    if page:
        st.session_state["goto_page"] = page


name = svc.identity_get_name()
if name is None:
    ui.page_header("Chat", "Type or speak a command in English, Hindi, Gujarati or a mix.")
    ui.first_run_form()
    st.stop()

if "cid" not in st.session_state or not svc.conversation_exists(st.session_state["cid"]):
    st.session_state["cid"] = svc.context_latest_conversation()
cid = st.session_state["cid"]
st.session_state.setdefault("mode", "cowork")
mode = st.session_state["mode"]


def open_conversation(conversation_id: int) -> None:
    st.session_state["cid"] = conversation_id
    st.session_state.pop("conv_action", None)
    st.rerun()


# Conversations in the sidebar: new chat, search, then the list; each row has a menu with Rename and Delete.
with st.session_state.get("page_sidebar") or st.sidebar:
    st.markdown('<p class="adhy-nav-section">Conversations</p>', unsafe_allow_html=True)
    if st.button("New chat", icon=":material/edit_square:", key="conv_new", width="stretch"):
        open_conversation(svc.conversation_new(cid))
    _q = st.text_input("Search conversations", key="conv_search", placeholder="Search conversations",
                       label_visibility="collapsed", icon=":material/search:", type="search")
    _convs = svc.conversations_list(_q, keep=cid)
    if not _convs:
        st.caption("No conversation matches." if _q.strip() else "No conversations yet.")
    _action = st.session_state.get("conv_action") or (None, None)
    for _c in _convs:
        with st.container(horizontal=True, vertical_alignment="center", gap=None, key=f"convrow_{_c['id']}"):
            if st.button(_c["title"], key=f"conv_{_c['id']}", type="secondary" if _c["id"] == cid else "tertiary",
                         width="stretch"):
                open_conversation(_c["id"])
            _do = st.menu_button("", ["Rename", "Delete"], icon=":material/more_horiz:", type="tertiary",
                                 key=f"convmenu_{_c['id']}", help="Rename or delete")
            if _do:
                st.session_state["conv_action"] = _action = (_do, _c["id"])
        if _action == ("Rename", _c["id"]):
            with st.form(f"rename_{_c['id']}", border=False):
                _t = st.text_input("New name", value=_c["title"], max_chars=60)
                _r1, _r2 = st.columns(2)
                if _r1.form_submit_button("Save", type="primary", width="stretch"):
                    if svc.conversation_rename(_c["id"], _t):
                        st.session_state.pop("conv_action", None)
                        st.rerun()
                    st.error("Enter a name.")
                if _r2.form_submit_button("Cancel", width="stretch"):
                    st.session_state.pop("conv_action", None)
                    st.rerun()
        if _action == ("Delete", _c["id"]):
            with st.container(border=True):
                st.markdown(f"Delete **{_c['title']}**? Its messages are removed for good.")
                _d1, _d2 = st.columns(2)
                if _d1.button("Delete", type="primary", key=f"convdel_{_c['id']}", width="stretch"):
                    svc.conversation_delete(_c["id"])
                    if _c["id"] == cid:
                        _rest = [c["id"] for c in _convs if c["id"] != cid]
                        cid = _rest[0] if _rest else svc.conversation_new()
                    open_conversation(cid)
                if _d2.button("Cancel", key=f"convkeep_{_c['id']}", width="stretch"):
                    st.session_state.pop("conv_action", None)
                    st.rerun()

history = svc.context_history(cid, 50)

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

steps = svc.turn_steps(history)  # which tools ran for each reply, from the audit log
last_user = next((m for m in reversed(history) if m["role"] == "user"), None)
last_reply = next((m for m in reversed(history) if m["role"] == "assistant"), None)
regen_ok = last_reply is not None and svc.can_regenerate(cid)
# While Regenerate or Edit runs (below, where typed messages are handled), the turn it replaces is not drawn.
_act = st.session_state.get("msg_action")
hide_from = None
if _act and _act[0] == "regenerate" and last_reply is not None:
    hide_from = last_reply["id"]
elif _act and _act[0] == "edit" and last_reply is not None and last_reply["id"] not in steps and not svc.pending_confirm(cid):
    hide_from = _act[1]
elif _act and _act[0] == "edit" and last_reply is None:
    hide_from = _act[1]


def copy_button(m: dict) -> None:
    """Copy: the text in a code box whose own copy icon puts it on the clipboard (no script needed)."""
    with st.popover("", icon=":material/content_copy:", type="tertiary", help="Copy"):
        st.code(m["content"], language=None, wrap_lines=True)
        st.caption("Use the copy icon at the top right of the box.")


for m in history:
    if hide_from is not None and m["id"] >= hide_from:
        break
    with st.chat_message(m["role"]):
        if m["role"] == "user" and st.session_state.get("editing") == m["id"]:
            with st.form(f"edit_{m['id']}", border=False):
                new_text = st.text_area("Edit message", value=m["content"], label_visibility="collapsed")
                e1, e2, _ = st.columns([1, 1, 4])
                if e1.form_submit_button("Send", type="primary"):
                    st.session_state.pop("editing", None)
                    st.session_state["msg_action"] = ("edit", m["id"], new_text)
                    st.rerun()
                if e2.form_submit_button("Cancel"):
                    st.session_state.pop("editing", None)
                    st.rerun()
            continue
        for s in steps.get(m["id"], []):  # one collapsed line per tool that ran, with its result
            with st.status(f"{s['action'].capitalize()}: {s['outcome']}", type="step", state=s["state"]):
                if s["target"]:
                    st.code(s["target"], language=None, wrap_lines=True)
                st.caption(f"Result: {s['result']}. {s['level']}"
                           + (f", {s['confirmed']}" if s["confirmed"] != "none" else "") + ".")
        st.markdown(m["content"])
        with st.container(horizontal=True, gap="small", key=f"actions_{m['id']}"):
            copy_button(m)
            if m["role"] == "user" and last_user is not None and m["id"] == last_user["id"]:
                if st.button("", icon=":material/edit:", type="tertiary", key=f"editbtn_{m['id']}",
                             help="Edit and send again"):
                    st.session_state["editing"] = m["id"]
                    st.rerun()
            if m["role"] == "assistant" and regen_ok and m["id"] == last_reply["id"]:
                if st.button("", icon=":material/refresh:", type="tertiary", key=f"regen_{m['id']}",
                             help="Regenerate: ask again for a new answer"):
                    st.session_state["msg_action"] = ("regenerate",)
                    st.rerun()
            if m["role"] == "assistant" and st.button("", icon=":material/flag:", type="tertiary",
                                                      key=f"wrong_{m['id']}", help="Wrong intent? Correct it"):
                st.session_state[f"correcting_{m['id']}"] = True
                st.rerun()
        if m["role"] == "assistant":
            intent_val = m.get("intent") or "unknown"
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

live = st.container()  # the turn being answered now is drawn here

# Spoken replies, only when "Reply with voice" is on in Settings. Listening (microphone, hands-free, wake word) lives
# on the Voice page; here a hidden speaker reads each new reply aloud and never listens.
last = next((m for m in reversed(history) if m["role"] == "assistant"), None)
last_id = last["id"] if last else 0
st.session_state.setdefault("seen_assistant", last_id)
new_reply = last is not None and last_id != st.session_state["seen_assistant"]
if svc.get_bool("voice_reply"):
    speak = new_reply
    vcmd = st.session_state.get("voice_cmd") or {}
    if vcmd.get("action") not in ("quiet", "lang"):
        vcmd = {}  # only "stop speaking" and the language reach the speaker; listening is on the Voice page
    _speak_text = last["content"] if speak else ""
    if speak and (last.get("intent") == "agent_confirm" or "Confirm or cancel" in _speak_text) and "say yes" not in _speak_text.lower():
        _speak_text = _speak_text.replace("Confirm or cancel.", "").strip() + " " + svc.speech_confirm_prompt(svc.get("voice_lang"))
    with st.container(key="voice_speaker"):
        svc.bridge_voice_input(theme_name=svc.get("theme") or "light", lang=svc.get("voice_lang") or "en-IN",
                               speak_text=_speak_text, speak_nonce=str(last_id) if speak else "",
                               command=vcmd or None, command_nonce=vcmd.get("nonce", ""),
                               handsfree_default=False, wake_default=False, key="chat_speaker")
if new_reply:
    st.session_state["seen_assistant"] = last_id

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
        else:
            st.session_state["action_note"] = _tr.message
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

_act = st.session_state.pop("msg_action", None)
if _act:  # Regenerate or Edit and send, chosen on a message above
    with live:
        if _act[0] == "edit":
            with st.chat_message("user"):
                st.markdown(_act[2])
        with st.spinner("Working"):
            result = (svc.regenerate(cid, mode) if _act[0] == "regenerate"
                      else svc.edit_and_resend(cid, _act[1], _act[2], mode))
        if result.ok and result.data.get("stream") is not None:
            with st.chat_message("assistant"):
                st.write_stream(result.data["stream"])
        elif not result.ok and result.error_code in ("E_BLOCKED", "E_BAD_ARGUMENTS"):
            st.session_state["action_note"] = result.message
    if result.ok:
        apply_ui_hints(result)
    st.rerun()
if st.session_state.get("action_note"):
    st.toast(st.session_state.pop("action_note"))

_goto = st.session_state.pop("goto_page", None)
if _goto in ("vision", "performance", "voice"):
    st.switch_page(f"app_pages/{_goto}.py")

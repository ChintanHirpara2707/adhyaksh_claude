"""Voice page: a large orb that follows the assistant's live state, a transcript, stop, spoken replies and spoken
confirmations. Talks through the background engine's native voice when it runs, else the browser microphone."""
import time

import streamlit as st

from adhyaksh.services import voice as svc
from adhyaksh.ui import components as ui

ui.chat_width()
ui.page_header("Voice", "Speak a command. The orb shows what the assistant is doing.")
if svc.identity_get_name() is None:
    ui.first_run_form()
    st.stop()

if "cid" not in st.session_state:
    st.session_state["cid"] = svc.latest_conversation()
cid = st.session_state["cid"]
mode = st.session_state.get("mode", "cowork")
native = bool(svc.engine_voice().get("running"))


@st.fragment(run_every=1)
def orb() -> None:
    s = svc.state()
    st.html(ui.orb_html(s["state"], s["detail"]))


orb()

history = svc.history(cid, 10)
last = next((m for m in reversed(history) if m["role"] == "assistant"), None)
last_id = last["id"] if last else 0
st.session_state.setdefault("voice_seen", last_id)

# Controls
left, right = st.columns(2)
if native:
    st.caption("The background engine is listening: say the wake word, or press Talk now.")
    if left.button("Talk now", type="primary", icon=":material/mic:", width="stretch"):
        res = svc.push_to_talk()
        if not res.ok:
            st.error(res.message)
    if right.button("Stop speaking", icon=":material/stop_circle:", width="stretch", key="stop_native"):
        svc.stop_speaking_engine()
else:
    if right.button("Stop speaking", icon=":material/stop_circle:", width="stretch", key="stop_browser"):
        st.session_state["voice_page_cmd"] = {"action": "quiet", "nonce": str(time.time_ns())}

# Spoken confirmation: large Yes and No, and the question is read out.
pending = svc.pending_confirm(cid)
if pending:
    with st.container(border=True):
        st.markdown(f"**{pending['action'].replace('_', ' ').capitalize()}**")
        st.code(pending["target"], language=None)
        st.caption("Say yes or no, or press a button.")
        y, n = st.columns(2)
        if y.button("Yes, do it", type="primary", width="stretch", key=f"vyes_{pending['token']}"):
            svc.confirm(cid, True)
            st.rerun()
        if n.button("No, cancel", width="stretch", key=f"vno_{pending['token']}"):
            svc.confirm(cid, False)
            st.rerun()

if not native:
    # Speak each new reply (this page is for voice, so replies are always read out).
    new_reply = last is not None and last_id != st.session_state["voice_seen"]
    speak_text = last["content"] if new_reply else ""
    if new_reply and pending and "say yes" not in speak_text.lower():
        speak_text = speak_text.replace("Confirm or cancel.", "").strip() + " " + svc.confirm_prompt(svc.get("voice_lang"))
    cmd = st.session_state.get("voice_page_cmd") or {}
    heard = svc.voice_input(theme_name=svc.get("theme") or "light", lang=svc.get("voice_lang") or "en-IN",
                            speak_text=speak_text, speak_nonce=str(last_id) if new_reply else "", key="voice_page",
                            status=st.session_state.pop("voice_page_status", ""),
                            command=cmd or None, command_nonce=cmd.get("nonce", ""),
                            handsfree_default=svc.get_bool("voice_handsfree"), wake_default=svc.get_bool("voice_wake_word"))
    if new_reply:
        st.session_state["voice_seen"] = last_id
    if heard and heard.get("nonce") != st.session_state.get("voice_page_nonce") and not heard.get("setting"):
        st.session_state["voice_page_nonce"] = heard["nonce"]
        if heard.get("audio_b64"):
            with st.spinner("Transcribing on this laptop"):
                out = svc.handle_audio(heard["audio_b64"], heard.get("lang", "en-IN"), bool(heard.get("handsfree")),
                                       bool(heard.get("wake")))
            heard["text"] = out.get("text") or ""
            if not heard["text"]:
                st.session_state["voice_page_status"] = out.get("error") or "Yes? I am listening"
                st.rerun()
        if heard.get("text"):
            with st.spinner("Working"):
                svc.handle_message(heard["text"], cid, voice=True, mode=mode)
            st.rerun()

# Transcript
st.subheader("Transcript")
if not history:
    ui.empty_state("Nothing said yet. Try: what time is it, open notepad, or remember that my car is Audi.")
for m in history:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])

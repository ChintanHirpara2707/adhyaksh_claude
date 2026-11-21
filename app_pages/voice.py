"""Voice page: a large orb that follows the assistant's live state, a transcript, stop, spoken replies and spoken
confirmations. Talks through the background engine's native voice when it runs, else the browser microphone."""

import streamlit as st

from adhyaksh.services import voice as svc
from adhyaksh.ui import components as ui

ui.chat_width()
ui.page_header("Voice", "Speak a command. The orb shows what the assistant is doing.")
if svc.identity_get_name() is None:
    ui.first_run_form()
    st.stop()

cid = svc.current_chat()  # the chat open in this server run, shared with Chat; None until the first message
mode = st.session_state.get("mode", "cowork")
native = bool(svc.engine_voice().get("running"))


@st.fragment(run_every=1)
def orb() -> None:
    s = svc.state()
    st.html(ui.orb_html(s["state"], s["detail"]))


orb()

# The same setting as Settings, Voice replies: on, replies are read aloud; off, text only.
_speak_on = st.toggle("Reply with voice", value=svc.get_bool("voice_reply"), key="voice_page_reply",
                      help="Off: replies stay text only, even after a spoken command. Same switch as in Settings.")
if _speak_on != svc.get_bool("voice_reply"):
    svc.set_value("voice_reply", "true" if _speak_on else "false")

# Only this server run: blank after the server starts, kept across F5 (older talk stays in Chat and Activity).
history = svc.transcript(cid)
last = next((m for m in reversed(history) if m["role"] == "assistant"), None)
last_id = last["id"] if last else 0
st.session_state.setdefault("voice_seen", last_id)

# Controls: with engine voice the page offers talk and stop; the browser voice control below has its own.
if native:
    st.caption("The background engine is listening: say the wake word, or press Talk now.")
    left, right = st.columns(2)
    if left.button("Talk now", type="primary", icon=":material/mic:", width="stretch"):
        res = svc.push_to_talk()
        if not res.ok:
            st.error(res.message)
    if right.button("Stop speaking", icon=":material/stop_circle:", width="stretch", key="stop_native"):
        svc.stop_speaking_engine()

# Spoken confirmation: large Yes and No, and the question is read out.
pending = svc.pending_confirm(cid) if cid else None
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
    # Each new reply is read out when "Reply with voice" is on; off, it is shown as text only.
    new_reply = last is not None and last_id != st.session_state["voice_seen"]
    speak = new_reply and _speak_on
    speak_text = last["content"] if speak else ""
    if speak and pending and "say yes" not in speak_text.lower():
        speak_text = speak_text.replace("Confirm or cancel.", "").strip() + " " + svc.confirm_prompt(svc.get("voice_lang"))
    heard = svc.voice_input(theme_name=svc.get("theme") or "light", lang=svc.get("voice_lang") or "en-IN",
                            speak_text=speak_text, speak_nonce=str(last_id) if speak else "", key="voice_page",
                            status=st.session_state.pop("voice_page_status", ""),
                            handsfree_default=svc.get_bool("voice_handsfree"), wake_default=svc.get_bool("voice_wake_word"))
    if new_reply:
        st.session_state["voice_seen"] = last_id
    if heard and heard.get("nonce") != st.session_state.get("voice_page_nonce") and heard.get("setting"):
        # Hands-free or the wake word was switched in the control: remember it for next time.
        st.session_state["voice_page_nonce"] = heard["nonce"]
        svc.set_value("voice_handsfree", "true" if heard.get("handsfree") else "false")
        svc.set_value("voice_wake_word", "true" if heard.get("wake") else "false")
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
                svc.handle_message(heard["text"], svc.ensure_chat(), voice=True, mode=mode)
            st.rerun()

# Transcript
st.subheader("Transcript")
if not history:
    ui.empty_state("Nothing said yet in this session. Try: what time is it, open notepad, or remember that my car "
                   "is Audi. Earlier conversations are in the Chat sidebar and on the Activity page.")
for m in history:
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
ui.scroll_anchor("adhy-voice-end")
# Bring the newest line into view when an exchange arrives or the log is (re)loaded, once per newest line.
if history and st.session_state.get("voice_scrolled_to") != history[-1]["id"]:
    st.session_state["voice_scrolled_to"] = history[-1]["id"]
    ui.scroll_to("adhy-voice-end", f"voice-{history[-1]['id']}")

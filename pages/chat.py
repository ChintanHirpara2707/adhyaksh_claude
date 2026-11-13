import streamlit as st
import time

from adhyaksh import config, db
from adhyaksh.chat import context, engine, identity
from adhyaksh.nlu import dataset
from adhyaksh.rag import loader
from adhyaksh.ui import components as ui
from adhyaksh.voice import bridge

ui.chat_width()
ui.page_header("Chat", "Type or speak a command in English, Hindi, Gujarati or a mix.")
if identity.get_name() is None:
    ui.first_run_form()
    st.stop()

if "cid" not in st.session_state:
    st.session_state["cid"] = context.latest_conversation()
cid = st.session_state["cid"]
st.session_state.setdefault("mode", "cowork")
mode = st.session_state["mode"]
if st.button("New conversation"):
    st.session_state["cid"] = context.new_conversation()
    st.rerun()

history = context.history(cid, 50)
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
                correct = st.selectbox("Correct intent", dataset.INTENTS,
                                       index=dataset.INTENTS.index(intent_val)
                                       if intent_val in dataset.INTENTS else 0,
                                       key=f"intent_{m['id']}")
                if st.button("Save correction", key=f"save_{m['id']}"):
                    db.execute(
                        "INSERT INTO feedback(message_id, correct_intent, note, created_at) "
                        "VALUES(?,?,?,?)",
                        (m["id"], correct, "", db.utcnow()))
                    st.session_state[f"correcting_{m['id']}"] = False
                    st.success("Correction saved. Retrain to use it.")
                    st.rerun()

# Show the agent steps live (collapsible), attached to the latest turn.
# ctx = context.get(cid)
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

with st.expander("Attached documents"):
    _docs = loader.list_documents()
    if not _docs:
        st.caption("None yet. Use the paperclip in the message box to attach a file.")
    for _d in _docs:
        _c1, _c2 = st.columns([5, 1])
        _c1.caption(f"{_d['filename']} - {_d['chunks']} passages")
        if _c2.button("Remove", key=f"rmdoc_{_d['id']}"):
            loader.delete_document(int(_d["id"]))
            st.rerun()

pending = context.get(cid).pending_confirm
if pending:
    choice = ui.confirmation_card(pending["action"].replace("_", " "), pending["target"], key=f"c_{pending['token']}")
    if choice:
        engine.confirm(cid, choice == "confirm")
        st.rerun()

last = next((m for m in reversed(history) if m["role"] == "assistant"), None)
last_id = last["id"] if last else 0
st.session_state.setdefault("seen_assistant", last_id)
speak = config.get_bool("voice_reply") and last is not None and last_id != st.session_state["seen_assistant"]
heard = bridge.voice_input(theme_name=config.get("theme") or "light", speak_text=last["content"] if speak else "",
                           speak_nonce=str(last_id) if speak else "")
if speak:
    st.session_state["seen_assistant"] = last_id
if heard and heard.get("nonce") != st.session_state.get("voice_nonce"):
    st.session_state["voice_nonce"] = heard["nonce"]
    st.caption(f"Heard: {heard['text']}")
    st.session_state["suggest_switch"] = False
    with st.spinner("Working"):
        result = engine.handle_message(heard["text"], cid, voice=True, mode=mode)
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

prompt = st.chat_input("Type a command or attach a PDF, DOCX or TXT file", accept_file="multiple",
                       file_type=["pdf", "docx", "txt", "md", "csv"])
if prompt:
    text = (getattr(prompt, "text", None) if not isinstance(prompt, str) else prompt) or ""
    files = [] if isinstance(prompt, str) else [(f.name, f.getvalue()) for f in (prompt.files or [])]
    st.session_state["suggest_switch"] = False
    with st.spinner("Working"):
        result = engine.handle_message(text, cid, mode=mode, attachments=files)
    if result.data and result.data.get("suggest_mode") == "cowork":
        st.session_state["suggest_switch"] = True
    st.rerun()

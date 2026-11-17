import json

import streamlit as st

from adhyaksh import __version__, config, db
from adhyaksh.llm import base as llm
from adhyaksh.nlu import evaluate, registry
from adhyaksh.rag import retriever
from adhyaksh.tools import apps
from adhyaksh.ui import components as ui

ui.page_header("Settings", "Folders, models, language model access, applications and your data.")
st.caption(f"Version {__version__}. Data folder: {config.data_dir()}. Database schema {db.schema_version()}.")

st.subheader("Folders")
with st.form("folders"):
    allowed = st.text_area("Allowed folders (one per line)", value="\n".join(str(p) for p in config.get_allowed_roots()))
    default = st.text_input("Default work folder", value=config.get("default_work_folder"))
    if st.form_submit_button("Save folders", type="primary"):
        ok, msg = config.configure_folders(allowed.splitlines(), default)
        (st.toast if ok else st.error)(msg)

st.subheader("Assistant")
runs = evaluate.latest_runs()
with st.form("assistant"):
    tau = st.slider("Confidence threshold", 0.10, 0.95, config.get_float("confidence_threshold"), 0.05)
    options = {r["name"]: r["model_id"] for r in runs}
    current = next((r["name"] for r in runs if r["is_active"]), None)
    model = st.selectbox("Active intent model", list(options) or ["No trained model"], index=list(options).index(current) if current else 0)
    voice = st.checkbox("Speak replies aloud (browser voice)", value=config.get_bool("voice_reply"))
    if st.form_submit_button("Save assistant settings", type="primary"):
        config.set_value("confidence_threshold", f"{tau:.2f}")
        config.set_value("voice_reply", "true" if voice else "false")
        if model in options:
            registry.set_active(options[model])
        st.toast("Saved.")

st.subheader("Language model and cloud use")
st.caption(f"Document retrieval method: {'Gemini embeddings' if retriever.embedding_mode() == 'gemini' else 'TF-IDF (offline)'}. "
           "Nothing leaves this computer unless you grant consent below and add a key.")
with st.form("llm"):
    provider = st.selectbox("Provider", ["", "groq", "gemini", "ollama"],
                            index=["", "groq", "gemini", "ollama"].index(config.get("llm_provider")),
                            format_func=lambda x: {"": "None (offline mode)", "ollama": "Ollama (local, free, no key)"}.get(x, x))
    existing = llm.api_key(provider) if provider else ""
    key = st.text_input("API key", type="password", placeholder=llm.mask(existing) if existing else "Not set")
    groq_model = st.text_input("Groq model", value=config.get("groq_model"))
    gemini_model = st.text_input("Gemini model", value=config.get("gemini_model"))
    ollama_model = st.text_input("Ollama model (installed locally, e.g. llama3.2:3b)", value=config.get("ollama_model"))
    embed_model = st.text_input("Gemini embedding model", value=config.get("embedding_model"))
    consent = st.checkbox("Allow sending questions and passages to the selected cloud provider (Groq, Gemini, Wikipedia lookup)", value=config.get_bool("cloud_consent"))
    agent_on = st.checkbox("Let the language model use tools (agent). Every action still passes the safety gateway",
                           value=config.get("agent_mode") != "off")
    if st.form_submit_button("Save language model settings", type="primary"):
        config.set_value("agent_mode", "auto" if agent_on else "off")
        config.set_value("llm_provider", provider)
        config.set_value("groq_model", groq_model.strip())
        config.set_value("gemini_model", gemini_model.strip())
        config.set_value("ollama_model", ollama_model.strip())
        config.set_value("embedding_model", embed_model.strip())
        config.set_value("cloud_consent", "true" if consent else "false")
        if provider in llm.PROVIDERS and key.strip():
            llm.set_key(provider, key)
        st.toast("Saved.")
if config.get_bool("cloud_consent") and config.get("llm_provider") in llm.PROVIDERS:
    st.warning("Cloud use is ON. Questions and document passages may be sent to the selected provider.")

st.subheader("Voice")
from adhyaksh.voice import stt  # noqa: E402
with st.form("voice"):
    _engine = st.radio("Speech recognition", ["browser", "local"], horizontal=True,
                       index=0 if config.get("stt_engine") != "local" else 1,
                       format_func=lambda x: {"browser": "Browser (Chrome or Edge; online in Chrome)",
                                              "local": "On this laptop (faster-whisper; offline, private)"}[x])
    _size = st.selectbox("Local speech model", list(stt.SIZES), index=list(stt.SIZES).index(stt.model_size()),
                         format_func=lambda k: f"{k} ({stt.SIZES[k]})")
    _rate = st.slider("Speaking speed", 0.6, 1.6, float(config.get("tts_rate") or 1.0), 0.1)
    _voice = st.text_input("Preferred voice name (blank = best available for the language)", value=config.get("tts_voice"),
                           help="For example 'Microsoft Swara Online (Natural) - Hindi (India)' in Edge.")
    _barge = st.checkbox("Stop speaking when I start talking (barge-in)", value=config.get_bool("voice_barge_in"))
    _wake = st.text_input("Extra wake words (comma separated)", value=config.get("wake_words"))
    if st.form_submit_button("Save voice settings", type="primary"):
        config.set_value("stt_engine", _engine)
        config.set_value("stt_model", _size)
        config.set_value("tts_rate", f"{_rate:.1f}")
        config.set_value("tts_voice", _voice.strip())
        config.set_value("voice_barge_in", "true" if _barge else "false")
        config.set_value("wake_words", _wake.strip())
        st.toast("Saved.")
if config.get("stt_engine") == "local":
    if not stt.installed():
        st.warning("Local speech recognition needs `pip install faster-whisper` (about 140 MB). The browser engine is used until then.")
    elif not stt.model_present():
        if st.button(f"Download the '{stt.model_size()}' speech model ({stt.SIZES[stt.model_size()].split(',')[0]})"):
            with st.spinner("Working"):
                _ok, _msg = stt.download()
            (st.success if _ok else st.error)(_msg)
    else:
        st.caption(f"Local speech model '{stt.model_size()}' is ready. Audio never leaves this laptop.")

st.subheader("Document search")
from adhyaksh.rag import embedder  # noqa: E402
_mode = retriever.embedding_mode()
st.caption("Current method: " + {"local": "local multilingual embeddings", "gemini": "Gemini embeddings (cloud)",
                                 "tfidf": "TF-IDF keywords (offline)"}[_mode]
           + ". Local embeddings find answers even when the question uses different words or another language. "
             "Sources indexed before a change of method keep working with keywords until they are attached again.")
if not embedder.installed():
    st.info("Optional: run `pip install fastembed` (about 28 MB) to enable local embeddings.")
elif not embedder.model_present():
    if st.button("Download the local embedding model (about 240 MB, one time)"):
        with st.spinner("Working"):
            _ok, _msg = embedder.download()
        (st.success if _ok else st.error)(_msg)
else:
    _use = st.checkbox("Use local embeddings for document search", value=config.get("embeddings_local") != "off")
    if _use != (config.get("embeddings_local") != "off"):
        config.set_value("embeddings_local", "auto" if _use else "off")
        st.rerun()

st.subheader("Power mode (dangerous)")
power = st.checkbox(
    "Enable run_python tool (execute Python code in the workspace)",
    value=config.get_bool("power_mode"),
    help="Power mode lets the agent run Python code. It is disabled by default. "
         "Code runs in a restricted sandbox with a 30 second timeout and requires "
         "confirmation every time. Every run is audited.",
)
if power:
    st.warning(
        "Power mode is ON. The run_python tool executes arbitrary Python code in a "
        "restricted sandbox. Use with caution. Every run requires confirmation and is audited."
    )
if st.button("Save power mode settings"):
    config.set_value("power_mode", "true" if power else "false")
    st.toast("Saved.")

st.subheader("Applications allow-list")
with st.form("apps"):
    text = st.text_area("JSON: name to command", value=json.dumps(apps.allowlist(), indent=2))
    minscore = st.slider("Minimum document match score", 0.05, 0.60, config.get_float("doc_min_score"), 0.01)
    if st.form_submit_button("Save", type="primary"):
        res = apps.set_allowlist(text)
        config.set_value("doc_min_score", f"{minscore:.2f}")
        if res.ok:
            st.toast("Saved.")
        else:
            st.error(res.message)

st.subheader("Your data")
st.download_button("Export my data (database copy)", data=db.export_bytes(), file_name="adhyaksh_export.db",
                   mime="application/octet-stream")
sure = st.checkbox("I understand that deleting all data cannot be undone")
if st.button("Delete all my data", disabled=not sure):
    db.wipe()
    registry.reload()
    st.session_state.clear()
    st.rerun()

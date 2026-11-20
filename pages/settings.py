import json

import streamlit as st

from adhyaksh.services import settings as svc
from adhyaksh.ui import components as ui

ui.page_header("Settings", "Folders, models, language model access, applications and your data.")
st.caption(f"Version {svc.version}. Data folder: {svc.data_dir()}. Database schema {svc.db_schema_version()}.")

st.subheader("Folders")
with st.form("folders"):
    allowed = st.text_area("Allowed folders (one per line)", value="\n".join(str(p) for p in svc.get_allowed_roots()))
    default = st.text_input("Default work folder", value=svc.get("default_work_folder"))
    if st.form_submit_button("Save folders", type="primary"):
        ok, msg = svc.configure_folders(allowed.splitlines(), default)
        (st.toast if ok else st.error)(msg)

st.subheader("Assistant")
runs = svc.evaluate_latest_runs()
with st.form("assistant"):
    tau = st.slider("Confidence threshold", 0.10, 0.95, svc.get_float("confidence_threshold"), 0.05)
    options = {r["name"]: r["model_id"] for r in runs}
    current = next((r["name"] for r in runs if r["is_active"]), None)
    model = st.selectbox("Active intent model", list(options) or ["No trained model"], index=list(options).index(current) if current else 0)
    voice = st.checkbox("Speak replies aloud (browser voice)", value=svc.get_bool("voice_reply"))
    if st.form_submit_button("Save assistant settings", type="primary"):
        svc.set_value("confidence_threshold", f"{tau:.2f}")
        svc.set_value("voice_reply", "true" if voice else "false")
        if model in options:
            svc.registry_set_active(options[model])
        st.toast("Saved.")

st.subheader("Language model and cloud use")
st.caption(f"Document retrieval method: {'Gemini embeddings' if svc.retriever_embedding_mode() == 'gemini' else 'TF-IDF (offline)'}. "
           "Nothing leaves this computer unless you grant consent below and add a key.")
with st.form("llm"):
    _providers = ["", "groq", "gemini", "ollama", "openai_compat"]
    provider = st.selectbox("Provider", _providers, index=_providers.index(svc.get("llm_provider")),
                            format_func=lambda x: {"": "None (offline mode)", "ollama": "Ollama (local, free, no key)",
                                                   "openai_compat": "OpenAI-compatible server (LM Studio, llama.cpp, vLLM, OpenRouter)"}.get(x, x))
    existing = svc.llm_api_key(provider) if provider else ""
    key = st.text_input("API key", type="password", placeholder=svc.llm_mask(existing) if existing else "Not set")
    groq_model = st.text_input("Groq model", value=svc.get("groq_model"))
    gemini_model = st.text_input("Gemini model", value=svc.get("gemini_model"))
    ollama_model = st.text_input("Ollama model (installed locally, e.g. llama3.2:3b)", value=svc.get("ollama_model"))
    compat_url = st.text_input("OpenAI-compatible base URL (a 127.0.0.1 address stays on this PC)", value=svc.get("openai_compat_url"))
    compat_model = st.text_input("OpenAI-compatible model name", value=svc.get("openai_compat_model"))
    _modes = ["auto", "native", "json"]
    tool_mode = st.selectbox("Tool calling", _modes, index=_modes.index(svc.get("llm_tool_mode")),
                             format_func=lambda x: {"auto": "Automatic (native when supported, else JSON)",
                                                    "native": "Native function calling only", "json": "JSON protocol only"}[x])
    _routes = ["local_first", "llm_first"]
    routing = st.selectbox("Simple commands", _routes, index=_routes.index(svc.get("routing")),
                           format_func=lambda x: {"local_first": "Run on this PC first (fast, private; the model handles the rest)",
                                                  "llm_first": "Always ask the language model"}[x])
    embed_model = st.text_input("Gemini embedding model", value=svc.get("embedding_model"))
    consent = st.checkbox("Allow sending questions and passages to the selected cloud provider (Groq, Gemini, Wikipedia lookup)", value=svc.get_bool("cloud_consent"))
    screen_consent = st.checkbox("Also allow the text read from my screen to go to the cloud provider (for 'explain my screen'). "
                                 "Off: only a model on this PC sees screen text; screenshots never leave the PC.",
                                 value=svc.get_bool("cloud_screen_consent"))
    agent_on = st.checkbox("Let the language model use tools (agent). Every action still passes the safety gateway",
                           value=svc.get("agent_mode") != "off")
    if st.form_submit_button("Save language model settings", type="primary"):
        svc.set_value("agent_mode", "auto" if agent_on else "off")
        svc.set_value("llm_provider", provider)
        svc.set_value("groq_model", groq_model.strip())
        svc.set_value("gemini_model", gemini_model.strip())
        svc.set_value("ollama_model", ollama_model.strip())
        svc.set_value("embedding_model", embed_model.strip())
        svc.set_value("openai_compat_model", compat_model.strip())
        svc.set_value("llm_tool_mode", tool_mode)
        svc.set_value("routing", routing)
        try:
            svc.set_value("openai_compat_url", compat_url.strip())
        except svc.SettingError as exc:
            st.error(str(exc))
        svc.set_value("cloud_consent", "true" if consent else "false")
        svc.set_value("cloud_screen_consent", "true" if screen_consent else "false")
        if provider in svc.PROVIDERS and key.strip():
            svc.llm_set_key(provider, key)
        st.toast("Saved.")
if svc.get_bool("cloud_consent") and svc.get("llm_provider") in svc.PROVIDERS:
    st.warning("Cloud use is ON. Questions and document passages may be sent to the selected provider.")

st.subheader("Voice")
with st.form("voice"):
    _engine = st.radio("Speech recognition", ["browser", "local"], horizontal=True,
                       index=0 if svc.get("stt_engine") != "local" else 1,
                       format_func=lambda x: {"browser": "Browser (Chrome or Edge; online in Chrome)",
                                              "local": "On this laptop (faster-whisper; offline, private)"}[x])
    _size = st.selectbox("Local speech model", list(svc.SIZES), index=list(svc.SIZES).index(svc.stt_model_size()),
                         format_func=lambda k: f"{k} ({svc.SIZES[k]})")
    _rate = st.slider("Speaking speed", 0.6, 1.6, float(svc.get("tts_rate") or 1.0), 0.1)
    _voice = st.text_input("Preferred voice name (blank = best available for the language)", value=svc.get("tts_voice"),
                           help="For example 'Microsoft Swara Online (Natural) - Hindi (India)' in Edge.")
    _barge = st.checkbox("Stop speaking when I start talking (barge-in)", value=svc.get_bool("voice_barge_in"))
    _wake = st.text_input("Extra wake words (comma separated)", value=svc.get("wake_words"))
    if st.form_submit_button("Save voice settings", type="primary"):
        svc.set_value("stt_engine", _engine)
        svc.set_value("stt_model", _size)
        svc.set_value("tts_rate", f"{_rate:.1f}")
        svc.set_value("tts_voice", _voice.strip())
        svc.set_value("voice_barge_in", "true" if _barge else "false")
        svc.set_value("wake_words", _wake.strip())
        st.toast("Saved.")
if svc.get("stt_engine") == "local":
    if not svc.stt_installed():
        st.warning("Local speech recognition needs `pip install faster-whisper` (about 140 MB). The browser engine is used until then.")
    elif not svc.stt_model_present():
        if st.button(f"Download the '{svc.stt_model_size()}' speech model ({svc.SIZES[svc.stt_model_size()].split(',')[0]})"):
            with st.spinner("Working"):
                _ok, _msg = svc.stt_download()
            (st.success if _ok else st.error)(_msg)
    else:
        st.caption(f"Local speech model '{svc.stt_model_size()}' is ready. Audio never leaves this laptop.")

st.subheader("Background engine")
st.caption("The engine keeps voice, reminders and the desktop HUD working without this browser tab. It listens on "
           f"127.0.0.1:{svc.get('server_port')} only and needs this PC's private token. Start it with: "
           "python -m adhyaksh.server")
st.caption("Engine: running. This console uses it." if svc.client_available() else "Engine: not running. This console works on its own.")
_use = st.toggle("Use the background engine when it is running", value=svc.get("background_engine") == "auto")
if _use != (svc.get("background_engine") == "auto"):
    svc.set_value("background_engine", "auto" if _use else "off")
    svc.client_forget_cache()
_voice = st.toggle("Listen for the wake word in the engine (native voice, local speech model only)",
                   value=svc.get_bool("voice_engine"),
                   help="Off by default. When on, the engine keeps the microphone open and acts only on phrases that start with "
                        "a wake word (Adhyaksh, ...). Audio never leaves this PC. Takes effect when the engine starts.")
if _voice != svc.get_bool("voice_engine"):
    svc.set_value("voice_engine", _voice)
_auto = st.toggle("Start the engine when Windows starts", value=svc.autostart_enabled(),
                  help="Adds one small file to your own Startup folder; no administrator rights. Turning it off deletes the file.")
if _auto != svc.autostart_enabled():
    _res = svc.autostart_enable() if _auto else svc.autostart_disable()
    st.toast("Done." if _res.ok else _res.message)

st.subheader("Document search")
_mode = svc.retriever_embedding_mode()
st.caption("Current method: " + {"local": "local multilingual embeddings", "gemini": "Gemini embeddings (cloud)",
                                 "tfidf": "TF-IDF keywords (offline)"}[_mode]
           + ". Local embeddings find answers even when the question uses different words or another language. "
             "Sources indexed before a change of method keep working with keywords until they are attached again.")
if not svc.embedder_installed():
    st.info("Optional: run `pip install fastembed` (about 28 MB) to enable local embeddings.")
elif not svc.embedder_model_present():
    if st.button("Download the local embedding model (about 240 MB, one time)"):
        with st.spinner("Working"):
            _ok, _msg = svc.embedder_download()
        (st.success if _ok else st.error)(_msg)
else:
    _use = st.checkbox("Use local embeddings for document search", value=svc.get("embeddings_local") != "off")
    if _use != (svc.get("embeddings_local") != "off"):
        svc.set_value("embeddings_local", "auto" if _use else "off")
        st.rerun()

st.subheader("Power mode (dangerous)")
power = st.checkbox(
    "Enable run_python tool (execute Python code in the workspace)",
    value=svc.get_bool("power_mode"),
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
    svc.set_value("power_mode", "true" if power else "false")
    st.toast("Saved.")

st.subheader("Applications allow-list")
with st.form("apps"):
    text = st.text_area("JSON: name to command", value=json.dumps(svc.apps_allowlist(), indent=2))
    minscore = st.slider("Minimum document match score", 0.05, 0.60, svc.get_float("doc_min_score"), 0.01)
    if st.form_submit_button("Save", type="primary"):
        res = svc.apps_set_allowlist(text)
        svc.set_value("doc_min_score", f"{minscore:.2f}")
        if res.ok:
            st.toast("Saved.")
        else:
            st.error(res.message)

st.subheader("Your data")
st.download_button("Export my data (database copy)", data=svc.db_export_bytes(), file_name="adhyaksh_export.db",
                   mime="application/octet-stream")
sure = st.checkbox("I understand that deleting all data cannot be undone")
if st.button("Delete all my data", disabled=not sure):
    svc.db_wipe()
    svc.registry_reload()
    st.session_state.clear()
    st.rerun()

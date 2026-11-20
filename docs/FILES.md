# Files — Folder map

## Root files

- `app.py` — Streamlit entry point: page routing, boot (logging + DB init), navigation.
- `run.bat` — Windows launcher: creates `.venv`, installs `requirements-core.txt`, runs Streamlit.
- `run.sh` — POSIX launcher: same as run.bat.
- `pytest.ini` — pytest configuration.
- `.env` — git-ignored; API keys for Groq/Gemini (never tracked).
- `.gitignore` — ignores `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.env`, `data/*.db`, `data/logs/`, `data/uploads/`, `models/*`, `*.zip`, `appmap.log`, `*.out`, `*.log`, `pytest_*.txt`, `*_dbg.txt`.
- `CLAUDE.md` — this file.
- `CHANGELOG.md`, `README.md`, `requirements-core.txt`, `requirements-optional.txt` (kept source files).

## Folders

- `.venv/` — git-ignored virtual environment (generated).
- `.streamlit/` — Streamlit config (generated).
- `.pytest_cache/` — git-ignored pytest cache (generated).
- `app_pages/` — Streamlit page modules (one per UI page).
- `adhyaksh/` — Python package root.
- `adhyaksh/__init__.py` — package marker, `__version__ = "0.1.0"`.
- `adhyaksh/config.py` — paths, constants, settings loader (all settings stored in SQLite).
- `adhyaksh/db.py` — SQLite access layer; schema, migrations, queries, backup/restore/export/wipe.
- `adhyaksh/logging_setup.py` — logging with secret redaction; writes to `data/logs/adhyaksh.log` (git-ignored).
- `adhyaksh/result.py` — `Result` dataclass and error codes (`E_*`).
- `adhyaksh/responses.py` — all user-facing reply templates (EN/HI/GU).
- `adhyaksh/nlu/lexicon.py`, `entities.py`, `frames.py` — multilingual verb and negation lexicon (shared with the data generator), entity extractors returning canonical values, and the frame parser (action + negation + target; negated commands are never run; pure action + target commands are routed here first).
- `adhyaksh/server.py` — background engine (FastAPI on 127.0.0.1; Host, Origin and token checks; /v1/message, /v1/confirm, /v1/pending, /v1/voice, WebSocket /v1/events). `adhyaksh/events.py` — in-process state and notice bus. `adhyaksh/watchdog.py` — battery, CPU, disk and reminder notices. `adhyaksh/client.py` — the console's link to the engine. `adhyaksh/autostart.py` — optional Startup-folder entry.
- `adhyaksh/voice/pipeline.py` — native voice: microphone, speech detection, local speech-to-text, wake words, push-to-talk, Windows voices, barge-in.
- `hud/` — desktop HUD: `core.py` (state, captions, backoff; no window), `app.py` (tkinter ring, engine link, global hotkey), `__main__.py`.
- `adhyaksh/agent/` — agent loop and tool registry: `__init__.py`, `registry.py` (tool registration, safety-guarded runner, run_python sandbox), `native.py` (agent loop, max 6 steps, L2 pause/resume, claim guard). Model turns go through `adhyaksh/llm/toolcall.py` (native tool calls or the JSON protocol, schema validation, self-repair).
- `adhyaksh/chat/` — chat engine: `__init__.py`, `context.py` (in-memory conversation context, pending slots/confirmations), `engine.py` (message routing, mode, OS_INTENTS, dispatch), `identity.py` (name extraction/save/get), `router.py` (rule layer, slot extractors, web command parsing, safe math).
- `adhyaksh/llm/` — LLM providers: `__init__.py`, `base.py` (Provider ABC, `ask`, `ask_with_tools`, Groq/Gemini selection, caching), `cache.py`, `groq.py`, `gemini.py`.
- `adhyaksh/memory/` — personal fact store: `facts.py` (statements, questions and forget requests in five styles as subject, attribute, value), `store.py` (save updates the same attribute, recall by attribute then similarity then words, forget through the gateway, automatic notes).
- `adhyaksh/nlu/` — intent models: `__init__.py`, `dataset.py` (intent dataset generation/validation/split), `features.py` (TF-IDF vectorizer), `models.py` (M1 logreg, M2 PyTorch MLP untested on target, M3 calibrated SVM), `registry.py` (SQLite model registry, predict with MIN_GAP), `train.py` (train all models, background run), `evaluate.py` (metrics, latency, threshold tuning, RESULTS.md writer).
- `adhyaksh/rag/` — document Q&A: `__init__.py`, `loader.py` (PDF/DOCX/TXT ingestion, chunking, SQLite storage), `chunker.py` (overlapping chunks), `retriever.py` (TF-IDF or Gemini embeddings), `answerer.py` (extractive or LLM answer with citations).
- `adhyaksh/safety/` — authorization: `__init__.py`, `policy.py` (L0-L3 levels, allowed folders, `run_guarded`, audit rule), `audit.py` (append-only audit log), `confirm.py` (confirmation token store), `verify.py` (post-condition checks after every action; retryable and hint on failures).
- `adhyaksh/tools/` — tool implementations: `__init__.py` (empty), `apps.py` (allow-listed app open/close), `boost.py` (PC stats, temp scan/clean), `files.py` (create/read/update/delete/search/list, send2trash), `office.py` (Excel/Word creation), `system.py` (status, screenshot, web open, special folder open), `audio.py` (speaker and mic volume, pycaw), `display.py` (brightness, WMI; fixed PowerShell runner), `network.py` (Wi-Fi and Bluetooth, WinRT radios), `power.py` (battery, lock, sleep, restart, shut down), `windows.py` (list, focus, minimize, maximize, restore, close windows), `screen.py` (look at the screen: capture, OCR, objects, explanation), `web.py` (read a page, search and answer; SSRF guard). `adhyaksh/persona.py` — the assistant's voice and capability text.
- `adhyaksh/ui/` — UI layer: `__init__.py`, `components.py` (page_header, empty_state, error_state, confirmation_card, first_run_form, chat_width), `icons.py` (page icon slugs), `theme.py` (light/dark design tokens, CSS, sidebar header).
- `adhyaksh/voice/` — browser speech: `__init__.py`, `bridge.py` (Streamlit component bridge, untested on target), `component/index.html` (Web Speech API recognition + synthesis).
- `adhyaksh/vision/` — object detection: `detector.py` (YOLOv8n/s/m, classify fallback, caching), `descriptions.py` (COCO descriptions + Wikipedia lookup).
- `tests/` — test suite: `__init__.py`, `helpers.py` (temporary workspace), `test_boost.py`, `test_chat.py`, `test_chat_regression.py`, `test_data_admin.py`, `test_dataset.py`, `test_db.py`, `test_guard.py`, `test_logging.py`, `test_models.py`, `test_modes.py`, `test_policy.py`, `test_rag.py`, `test_responses.py`, `test_routing_fixes.py`, `test_static.py`, `test_theme.py`, `test_tools.py`, `test_vision.py`, `test_web_commands.py`.
- `data/` — data directory (git-ignored `*.db`, `*.db-wal`, `*.db-shm`, `uploads/`, `logs/`, `backups/`). Contains `intents.csv` (training intents, unreviewed), `test_author.csv` (held-out author cases), `test_codemixed.csv` (held-out code-mixed test), `adhyaksh.db` (generated SQLite database).
- `models/` — trained model files (git-ignored except `.gitkeep`). Contains `m1_logreg.joblib`, `m3_svm.joblib`, `yolov8n.pt`, `yolov8n-cls.pt`, `yolov8s.pt`.
- `docs/` — documentation: `ASSUMPTIONS.md`, `CHANGELOG.md`, `DATA_CARD.md`, `DECISIONS.md`, `IDEAS.md`, `OPEN_QUESTIONS.md`, `PERFORMANCE.md`, `PROGRESS.md`, `PROJECT_BRIEF.md`, `QA_LOG.md`, `RESULTS.md` (generated by `evaluate.write_results_md()`), `FILES.md`, `CONFIG.md`, `TESTS.md`, `DATABASE.md`.

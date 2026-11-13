# CLAUDE.md

## 1. Overview

ADHYAKSH is a private, local-first, multilingual desktop assistant for a single operator on a Windows laptop. It accepts typed or spoken commands in English, Hindi, Gujarati, Hinglish and Gujlish, and can create/read/update/delete/search files, create Excel and Word files, open and close allow-listed applications, take screenshots, check system status, remember personal facts, answer questions from indexed documents, answer general knowledge questions via an optional cloud LLM (Groq or Gemini), and clean temporary files.

Target user: one operator who wants a local assistant that works without an API key for core commands, with optional cloud features only when explicitly consented.

Languages: English (en), Hindi (hi), Gujarati (gu), Hinglish, Gujlish. Language is detected per message by script (Devanagari = hi, Gujarati = gu, else en).

Free and local-first: the app works fully without any key. Intent models run locally (scikit-learn TF-IDF + LogisticRegression or calibrated SVM; optional PyTorch MLP untested on target). Retrieval is offline TF-IDF by default. Cloud LLM is used only when `cloud_consent` is enabled and a provider key is set in `.env`. API keys are read from environment or `.env`, never logged or stored in the database.

How to run:
- `run.bat` (Windows): creates `.venv` if missing using Python 3.12 or 3.11, installs `requirements-core.txt`, runs `streamlit run app.py`.
- `run.sh` (POSIX): same steps with `python3 -m venv venv`.
- Direct: `streamlit run app.py` from the project root with `.venv\Scripts\python` (Windows) or the activated venv.
Python version: 3.11 or 3.12.
Requirements files: `requirements-core.txt` (streamlit, numpy, pandas, scikit-learn, openpyxl, python-docx, PyMuPDF, psutil, send2trash, python-dotenv, requests, matplotlib, Pillow, pytest, pytest-cov). `requirements-optional.txt` (currently only comments; ultralytics was noted but not pinned).

## 2. Folder map

Root files:
- `app.py` — Streamlit entry point: page routing, boot (logging + DB init), navigation.
- `run.bat` — Windows launcher: creates `.venv`, installs `requirements-core.txt`, runs Streamlit.
- `run.sh` — POSIX launcher: same as run.bat.
- `pytest.ini` — pytest configuration.
- `.env` — git-ignored; API keys for Groq/Gemini (never tracked).
- `.gitignore` — ignores `.venv/`, `__pycache__/`, `*.pyc`, `.pytest_cache/`, `.env`, `data/*.db`, `data/logs/`, `data/uploads/`, `models/*`, `*.zip`, `appmap.log`, `*.out`, `*.log`, `pytest_*.txt`, `*_dbg.txt`.
- `CLAUDE.md` — this file.
- `CHANGELOG.md`, `README.md`, `check_model.py`, `check_model2.py`, `fix_boot.py`, `fix_router.py`, `repro_web.py`, `requirements-core.txt`, `requirements-optional.txt`, `line_dbg.txt`, `appmap.log` (git-ignored/generated).

Folders:
- `.venv/` — git-ignored virtual environment (generated).
- `.streamlit/` — Streamlit config (generated).
- `.pytest_cache/` — git-ignored pytest cache (generated).
- `pages/` — Streamlit page modules (one per UI page).
- `adhyaksh/` — Python package root.
- `adhyaksh/__init__.py` — package marker, `__version__ = "0.1.0"`.
- `adhyaksh/config.py` — paths, constants, settings loader (all settings stored in SQLite).
- `adhyaksh/db.py` — SQLite access layer; schema, migrations, queries, backup/restore/export/wipe.
- `adhyaksh/logging_setup.py` — logging with secret redaction; writes to `data/logs/adhyaksh.log` (git-ignored).
- `adhyaksh/result.py` — `Result` dataclass and error codes (`E_*`).
- `adhyaksh/responses.py` — all user-facing reply templates (EN/HI/GU).
- `adhyaksh/agent/` — agent loop and tool registry: `__init__.py`, `registry.py` (tool registration, safety-guarded runner, run_python sandbox), `runner.py` (agent loop: TOOL/ANSWER protocol, max 6 steps, L2 pause/resume).
- `adhyaksh/chat/` — chat engine: `__init__.py`, `context.py` (in-memory conversation context, pending slots/confirmations), `engine.py` (message routing, mode, OS_INTENTS, dispatch), `identity.py` (name extraction/save/get), `router.py` (rule layer, slot extractors, web command parsing, safe math).
- `adhyaksh/llm/` — LLM providers: `__init__.py`, `base.py` (Provider ABC, `ask`, `ask_with_tools`, Groq/Gemini selection, caching), `cache.py`, `groq.py`, `gemini.py`.
- `adhyaksh/memory/` — personal fact store: `__init__.py`, `store.py` (save/recall/list/update/delete facts, keyword recall).
- `adhyaksh/nlu/` — intent models: `__init__.py`, `dataset.py` (intent dataset generation/validation/split), `features.py` (TF-IDF vectorizer), `models.py` (M1 logreg, M2 PyTorch MLP untested on target, M3 calibrated SVM), `registry.py` (SQLite model registry, predict with MIN_GAP), `train.py` (train all models, background run), `evaluate.py` (metrics, latency, threshold tuning, RESULTS.md writer).
- `adhyaksh/rag/` — document Q&A: `__init__.py`, `loader.py` (PDF/DOCX/TXT ingestion, chunking, SQLite storage), `chunker.py` (overlapping chunks), `retriever.py` (TF-IDF or Gemini embeddings), `answerer.py` (extractive or LLM answer with citations).
- `adhyaksh/safety/` — authorization: `__init__.py`, `policy.py` (L0-L3 levels, allowed folders, `run_guarded`, audit rule), `audit.py` (append-only audit log), `confirm.py` (confirmation token store).
- `adhyaksh/tools/` — tool implementations: `__init__.py` (empty), `apps.py` (allow-listed app open/close), `boost.py` (PC stats, temp scan/clean), `files.py` (create/read/update/delete/search/list, send2trash), `office.py` (Excel/Word creation), `system.py` (status, screenshot, web open, special folder open).
- `adhyaksh/ui/` — UI layer: `__init__.py`, `components.py` (page_header, empty_state, error_state, confirmation_card, first_run_form, chat_width), `icons.py` (page icon slugs), `theme.py` (light/dark design tokens, CSS, sidebar header).
- `adhyaksh/voice/` — browser speech: `__init__.py`, `bridge.py` (Streamlit component bridge, untested on target), `component/index.html` (Web Speech API recognition + synthesis).
- `adhyaksh/vision/` — object detection: `detector.py` (YOLOv8n/s/m, classify fallback, caching), `descriptions.py` (COCO descriptions + Wikipedia lookup).
- `tests/` — test suite: `__init__.py`, `helpers.py` (temporary workspace), `test_boost.py`, `test_chat.py`, `test_chat_regression.py`, `test_data_admin.py`, `test_dataset.py`, `test_db.py`, `test_guard.py`, `test_logging.py`, `test_models.py`, `test_modes.py`, `test_policy.py`, `test_rag.py`, `test_responses.py`, `test_routing_fixes.py`, `test_static.py`, `test_theme.py`, `test_tools.py`, `test_vision.py`, `test_web_commands.py`.
- `data/` — data directory (git-ignored `*.db`, `*.db-wal`, `*.db-shm`, `uploads/`, `logs/`, `backups/`). Contains `intents.csv` (training intents, unreviewed), `test_author.csv` (held-out author cases), `test_codemixed.csv` (held-out code-mixed test), `adhyaksh.db` (generated SQLite database).
- `models/` — trained model files (git-ignored except `.gitkeep`). Contains `m1_logreg.joblib`, `m3_svm.joblib`, `yolov8n.pt`, `yolov8n-cls.pt`, `yolov8s.pt`.
- `docs/` — documentation: `ASSUMPTIONS.md`, `CHANGELOG.md`, `DATA_CARD.md`, `DECISIONS.md`, `IDEAS.md`, `OPEN_QUESTIONS.md`, `PERFORMANCE.md`, `PROGRESS.md`, `PROJECT_BRIEF.md`, `QA_LOG.md`, `RESULTS.md` (generated by `evaluate.write_results_md()`).

## 3. Pages and features

Each page file calls `ui.page_header(title, description)` and `theme.inject(config.get("theme") or "light")`.

- **Chat** (`pages/chat.py`): Type or speak a command. Shows message history with streaming for agent replies. "Wrong intent?" correction button per assistant reply (writes to `feedback` table). Voice input via `bridge.voice_input` (speak replies aloud if `voice_reply` enabled). Mode toggle (Chat/Cowork) stored in `st.session_state["mode"]`, passed to `engine.handle_message(..., mode=mode)`. When the engine returns `suggest_mode == "cowork"`, shows a "Switch to Cowork" button. Calls `engine.handle_message`, `engine.confirm`, `context.history`, `context.get`, `bridge.voice_input`, `dataset.INTENTS`.
- **Cowork**: Not a separate page; it is a mode (`mode="cowork"`) on the Chat page. In Cowork mode all OS_INTENTS (file/app/system tools) are allowed. In Chat mode they are refused with a `needs_cowork` reply and a "Switch to Cowork" button.
- **Voice**: Built into Chat via `adhyaksh/voice/bridge.py` and `adhyaksh/voice/component/index.html` (Web Speech API recognition + synthesis, wake word not implemented in the current HTML). Untested on target.
- **Documents** (`pages/documents.py`): Upload PDF/DOCX/TXT (up to 25 MB each), index them, list indexed documents, remove documents, ask questions with cited sources. Calls `loader.ingest_bytes`, `loader.list_documents`, `loader.delete_document`, `answerer.answer`, `retriever.embedding_mode`.
- **Memory** (`pages/memory.py`): Add facts ("remember that my car is Audi"), list/search facts, edit or delete facts. Calls `store.save_fact`, `store.list_facts`, `store.update_fact`, `store.delete_fact`.
- **Tools** (`pages/tools.py`): System status (CPU/RAM/disk), workspace file listing, app open/close with confirmation. Calls `system.status`, `files.list_dir`, `apps.open_app`, `apps.close_app`, `ui.confirmation_card`, `policy.cancel_guarded`.
- **Model Lab** (`pages/model_lab.py`): Model comparison table, confusion matrix, per-language metrics, add/correct dataset examples, background training. Calls `evaluate.latest_runs`, `registry.set_active`, `dataset.load`, `dataset.add_example`, `train.start_background`, `train.status`, `theme.resolve`.
- **Activity** (`pages/activity.py`): Append-only audit log of every action (ts, action, target, level, confirmed, result). Calls `audit.list_recent`.
- **Settings** (`pages/settings.py`): Folders (allowed roots, default work folder), Assistant (confidence threshold, active model, voice reply), Language model and cloud use (provider, API key, model names, cloud_consent), Power mode toggle, Applications allow-list JSON, Your data (export/wipe). Calls `config.*`, `db.*`, `evaluate.latest_runs`, `registry.set_active`, `llm.*`, `retriever.embedding_mode`, `apps.*`.
- **Object Detection** (`pages/vision.py`): Camera snapshot or file upload (JPG/PNG/WEBP). YOLOv8 detection with model choice (fast/balanced/accurate), image size slider, confidence slider, annotated image, grouped detection list with counts and best confidence, two-sentence descriptions, optional Wikipedia lookup, collapsible Details (size, file size, brightness, model, confidence, camera bytes, raw detections at 0.05). Classifier fallback ("Closest match") when detection finds nothing. Calls `detector.detect`, `detector.classify`, `detector.detect_raw`, `detector.average_brightness`, `descriptions.describe`, `descriptions.wikipedia`.
- **PC Performance** (`pages/performance.py`): Live gauges (fragment, refreshes every 3s): CPU %, RAM %, Disk %, Temp files MB. Boost PC button: scan_temp, then Clean now/Cancel buttons, shows freed MB and skipped count. Calls `boost.stats`, `boost.scan_temp`, `boost.clean_temp`.

## 4. Chat engine flow

From message to reply (`adhyaksh/chat/engine.py`):

1. `handle_message(text, conversation_id, voice=False, mode="cowork")` — trims text to `MAX_MESSAGE` (2000), detects language (`detect_lang`: Devanagari = hi, Gujarati = gu, else en), saves user message, calls `_process`, saves assistant reply, returns a `Result` dict with `reply`, `intent`, `confidence`, `action`, `latency_ms`, `confirmation`, `sources`, `lang`, `voice`, `mode`, and optionally `suggest_mode`.
2. `_process(text, ctx, convo_id, lang, mode="cowork")` — handles pending confirmations (agent, regular, name), explicit `agent:` invocation, pending slot resolution, rule-layer matching (`router.match_rules`), and model prediction (`registry.predict`). If confidence < threshold or gap < `registry.MIN_GAP` (0.10), routes to agent (if enabled) or knowledge answerer or returns `_cannot_do_yet`. If multi-step and agent enabled, routes to agent. Otherwise dispatches via `_dispatch`.
3. Mode: default is `"cowork"`. In `"chat"` mode, if the routed intent is in `OS_INTENTS` (file_create, file_read, file_update, file_delete, file_search, folder_create, office_create, app_open, app_close, special_folder_open, web_open, screenshot, system_status), `_dispatch` returns `_t("needs_cowork", lang)` with `suggest_mode="cowork"` and runs NO tool. Memory, document Q&A, knowledge, math, time/date, identity, small talk and unsupported replies work normally in both modes.
4. Rule layer (`adhyaksh/chat/router.py`): `match_rules` matches greetings, get_identity, bot_identity, time_date, math (safe_eval via ast + word-based math), file_create named, folder_create, screenshot, special_folder_open, web commands (`parse_web_command`), smalltalk, set_identity, pronoun references. Slot extractors: `extract_file_name`, `extract_folder_name`, `extract_url`, `find_app`, `find_special_folder`, `find_content`, `office_kind`, `find_count`.
5. `_dispatch(intent, text, slots, ctx, convo_id, lang, mode)` — routes to the appropriate handler for each intent (greet, bot_identity, smalltalk, time_date, math, help, set_identity, get_identity, memory_save, memory_recall, system_status, folder_create, screenshot, special_folder_open, web_open, app_open/app_close, office_create, file intents, doc_question, knowledge_question, out_of_scope, unknown).
6. File intents (`_file_intent`): file_create (adds .txt if missing), file_read, file_update (append/overwrite with L2 confirmation), file_delete (L2 confirmation via send2trash), file_search.
7. Slot resolution: rule-layer slots first; model-predicted intents use `_model_slots` which calls the same extractors as the rule layer. `_correct_file_folder` converts `file_create` to `folder_create` if folder words appear.
8. Agent (`adhyaksh/agent/runner.py`, `registry.py`): when enabled (cloud_consent + provider), runs a TOOL/ANSWER loop (max 6 steps, 8s timeout). Tool results wrapped as DATA blocks. L2 pauses for confirmation (`pending_agent_confirm`), resume via `agent_runner.resume`. Disabled without key/consent.
9. Knowledge: `doc_question` uses `answerer.answer` (extractive or LLM with citations); `knowledge_question` uses `_llm_answer` (provider.complete with brief prompt).
10. Catch-all error handler: `handle_message` wraps `_process` in try/except; on exception logs full traceback via `_LOG` to `logs/adhyaksh.log` (git-ignored) and returns `_t("error", lang, reason="internal error (X)")`.
11. Templates (`adhyaksh/responses.py`): `t(key, lang, **kwargs)` looks up `TEMPLATES[key]`, falls back to `variants["en"]`. Variants in en/hi/gu. Hindi and Gujarati translations are UNREVIEWED pending author review.

## 5. NLU models

Three intent models (`adhyaksh/nlu/models.py`):
- **M1 `m1_logreg`**: TF-IDF (word + char n-grams) + LogisticRegression (C=20.0).
- **M2 `m2_mlp`**: TF-IDF + PyTorch MLP (CPU, 256 hidden, dropout 0.3, 30s sandbox timeout). Marked UNTESTED ON TARGET (PyTorch could not be installed in the build sandbox).
- **M3 `m3_svm`**: TF-IDF + calibrated LinearSVC (CalibratedClassifierCV, sigmoid, cv=3). This is the production replacement for the embedding variant.

Features (`adhyaksh/nlu/features.py`): word TF-IDF (1-2 grams) + char_wb TF-IDF (2-5 grams) via FeatureUnion. Token pattern splits on whitespace/punctuation only, keeping Indic vowel signs inside words.

Registry (`adhyaksh/nlu/registry.py`): SQLite-backed model registry (`model_registry`, `eval_runs` tables). Cached active model in memory. `predict(text)` returns `(intent, confidence, gap_to_second)`. `MIN_GAP = 0.10` — if the gap between top two intents is smaller, the prediction is rejected as ambiguous (does not fall through to nearest intent). `available()` returns whether an active trained model exists.

Training (`adhyaksh/nlu/train.py`): `train_all(seed=42, kinds=[...])` trains all kinds, evaluates on held-out test split and code-mixed test set, tunes confidence threshold `tau` (smallest threshold with >=97% accepted accuracy and >=80% coverage), saves models to `models/`, registers in SQLite, sets the best model active (selected on validation macro-F1, never on test). Background training via `start_background` (single worker thread, debounced). CLI: `python -m adhyaksh.nlu.train --all`.

Evaluation (`adhyaksh/nlu/evaluate.py`): `compute_metrics` (accuracy, macro-F1, per-language F1, confusion matrix), `measure_latency` (p50/p95 ms), `tune_tau`, `latest_runs`, `write_results_md` (writes `docs/RESULTS.md`).

Data:
- `data/intents.csv` — training intents (columns: text, intent, language, script, source, reviewed). Generated rows marked `reviewed=false`. Languages: en, hi, gu, hinglish, gujlish. Scripts: latin, devanagari, gujarati. Source: generated, author, corrected. MIN_PER_INTENT=40, MIN_TOTAL=500, MIN_LANG_SHARE=0.15.
- `data/test_author.csv` — 28 author-reviewed held-out cases (source=author, reviewed=true; never trained on).
- `data/test_codemixed.csv` — held-out code-mixed test phrasings (hinglish/gujlish only, different wording from templates).

Metrics caveats: The held-out test split shares template families with training, so in-distribution scores are optimistic. The code-mixed file uses different wording and is the harder, more honest figure. Target macro-F1 0.85; results vary by run. Results are written to `docs/RESULTS.md` by `evaluate.write_results_md()`. The dataset is UNREVIEWED (author to review `data/intents.csv` and `data/test_codemixed.csv`).

## 6. Tools and safety

Tools (`adhyaksh/tools/`):
- **files** (`files.py`): create, read, update (append/overwrite), delete (send2trash to Recycle Bin or local trash fallback), search, list. Every function goes through `safety.policy.run_guarded`. `MAX_READ_BYTES = 1_000_000`, `MAX_SHOWN_CHARS = 20_000`. Paths resolved via `policy.check_path` against allowed roots.
- **office** (`office.py`): `create_workbook` (Excel .xlsx via openpyxl), `create_document` (Word .docx via python-docx), `names_example` (Indian names example). Opened with default OS app after creation unless `ADHYAKSH_NO_OPEN`.
- **apps** (`apps.py`): `open_app` / `close_app` restricted to allow-list (saved + merged defaults: Notepad, Calculator, Snipping Tool, File Explorer, Chrome, Edge, Brave, VS Code, WhatsApp, Spotify on Windows). WhatsApp falls back to `whatsapp:` URI. `close_app` is L2 (needs confirmation). Uses `os.startfile` / `subprocess.Popen`, never shell.
- **system** (`system.py`): `status` (psutil CPU/RAM/disk, cached 5s), `screenshot` (PIL ImageGrab), `web_open` (default browser), `open_special_folder` (Recycle Bin, Downloads, Documents, Desktop). `web_open`/`fetch_page` blocked for localhost/private IPs and non-http schemes.
- **boost** (`boost.py`): `stats()` (cpu_percent, ram_percent, ram_available_gb, disk_percent, disk_free_gb), `scan_temp(dir, min_age_hours=24)` (count old regular files in temp dir), `clean_temp(dir, min_age_hours=24)` (delete old files, remove empty subfolders, skip locked files silently, audit log L2 entry).

Safety levels (`adhyaksh/safety/policy.py`, `LEVELS`):
- L0 (read-only): file_list, file_read, file_search, memory_read, doc_query, system_status.
- L1 (reversible): file_create, file_append, office_create, app_open, memory_write, screenshot, web_open, special_folder_open.
- L2 (destructive, needs confirmation): file_overwrite, file_delete, app_close, memory_delete, run_python.
- L3 (blocked): shell_exec, unknown action types, system paths, modifying an allowed root folder.

Authorization (`policy.authorize`): pure function returning `Decision(level, allowed, needs_confirmation, reason)`. Enforces allowed folders via `check_path` (rejects system roots, user profile root, paths outside allowed roots). L2 actions need a confirmation token.

Confirmation flow: L2 tool calls create a pending confirmation token (`safety.confirm.STORE`), return `E_NEEDS_CONFIRM` with token. UI renders `ui.confirmation_card` with Confirm/Cancel. Confirm consumes the token and re-runs via `run_guarded` with `confirm_ctx`; Cancel calls `policy.cancel_guarded` and writes a "cancelled" audit row. Expired/invalid tokens return `E_CONFIRM_INVALID`.

Audit log (`adhyaksh/safety/audit.py`, `adhyaksh/db.py` `audit_log` table): append-only (SQLite triggers prevent UPDATE/DELETE). Every action attempt ends in exactly one row (executed, failed, blocked, rejected, cancelled). Columns: id, ts, user_text, intent, action, target, level, confirmed, result. Creating a pending confirmation is NOT an action (writes no row). Viewed on the Activity page.

send2trash: used by `files.delete` to move to Recycle Bin; falls back to a local trash folder under `data/` if `send2trash` is missing.

## 7. Memory and RAG

Memory (`adhyaksh/memory/store.py`): Personal facts stored in SQLite (`memory_facts` table). `save_fact(text)` strips prefixes ("remember that", "note down that", "save this", Hinglish/Gujlish equivalents), detects duplicates by normalized text, categorizes as "personal" if it starts with my/meri/etc., else "general". `recall(query)` does keyword overlap recall (token set intersection, skipping stop words). `list_facts(search)`, `update_fact`, `delete_fact` available. The Memory page lets users add/search/edit/delete facts.

RAG (`adhyaksh/rag/`): Document Q&A for indexed TXT/DOCX/PDF files.
- **loader** (`loader.py`): `ingest(path)` copies file to `data/uploads/`, extracts text (PDF via PyMuPDF `fitz`, DOCX via python-docx with heading-based sections, TXT via read_text), chunks via `chunker.chunk_text` (overlapping ~500 char chunks on whitespace boundaries), stores chunks in `doc_chunks` with optional Gemini embeddings (BLOB) or NULL (TF-IDF fallback). Max 25 MB per file. `ingest_bytes` for uploaded files. `list_documents`, `delete_document`.
- **chunker** (`chunker.py`): `chunk_text(text, size=500, overlap=100)` — splits on whitespace boundaries, overlapping chunks.
- **retriever** (`retriever.py`): `embedding_mode()` returns "gemini" only with gemini provider + key + cloud_consent, else "tfidf". `retrieve(question, k=4)` returns top-k chunks with scores (cosine similarity via Gemini embeddings or TF-IDF linear_kernel). Caches the TF-IDF index.
- **answerer** (`answerer.py`): `answer(question)` retrieves hits above `doc_min_score` threshold. If none, returns `doc_not_found`. If cloud_consent + provider available, uses LLM with passages; otherwise returns extractive answer with source citations (top 3 chunks). Returns `{answer, sources, mode, found}`.

SQLite schema (`adhyaksh/db.py`, `SCHEMA_V1`), every table and column:
- `profile(id INTEGER PRIMARY KEY, display_name TEXT NOT NULL, created_at TEXT NOT NULL)` — single-operator name profile.
- `settings(key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL)` — all settings key/value.
- `conversations(id INTEGER PRIMARY KEY, title TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL)` — conversation list.
- `messages(id INTEGER PRIMARY KEY, conversation_id INTEGER REFERENCES conversations(id) ON DELETE CASCADE, role TEXT NOT NULL, content TEXT NOT NULL, intent TEXT, confidence REAL, latency_ms REAL, created_at TEXT NOT NULL)` — chat history. Index `idx_messages_conv` on conversation_id.
- `memory_facts(id INTEGER PRIMARY KEY, fact TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'general', created_at TEXT NOT NULL, updated_at TEXT NOT NULL)` — remembered facts.
- `documents(id INTEGER PRIMARY KEY, filename TEXT NOT NULL, filepath TEXT NOT NULL, pages INTEGER, indexed_at TEXT, status TEXT NOT NULL DEFAULT 'pending')` — indexed documents.
- `doc_chunks(id INTEGER PRIMARY KEY, document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE, chunk_index INTEGER NOT NULL, page_or_section TEXT, text TEXT NOT NULL, embedding BLOB NULL, method TEXT NOT NULL DEFAULT 'tfidf')` — document chunks. Index `idx_chunks_doc` on document_id.
- `audit_log(id INTEGER PRIMARY KEY, ts TEXT NOT NULL, user_text TEXT, intent TEXT, action TEXT NOT NULL, target TEXT, level INTEGER NOT NULL, confirmed TEXT NOT NULL DEFAULT 'none', result TEXT NOT NULL)` — append-only audit. Triggers `audit_log_no_update` and `audit_log_no_delete` prevent changes.
- `model_registry(id INTEGER PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, path TEXT NOT NULL, dataset_hash TEXT, trained_at TEXT NOT NULL, is_active INTEGER NOT NULL DEFAULT 0)` — trained model registry.
- `eval_runs(id INTEGER PRIMARY KEY, model_id INTEGER REFERENCES model_registry(id) ON DELETE CASCADE, accuracy REAL, macro_f1 REAL, per_language_json TEXT, confusion_json TEXT, size_bytes INTEGER, p50_ms REAL, p95_ms REAL, created_at TEXT NOT NULL)` — evaluation results.
- `feedback(id INTEGER PRIMARY KEY, message_id INTEGER REFERENCES messages(id) ON DELETE CASCADE, correct_intent TEXT NOT NULL, note TEXT, created_at TEXT NOT NULL)` — "Wrong intent?" corrections.

`db.py` also provides: `connect()` context manager (WAL journal, foreign_keys=ON), `schema_version()`, `init()` (runs migrations), `execute()`, `executemany()`, `query_all()`, `query_one()`, `get_setting()`, `set_setting()`, `backup()`, `restore()`, `export_bytes()`, `wipe()`, `utcnow()`.

## 8. LLM and voice

LLM providers (`adhyaksh/llm/`):
- **Groq** (`groq.py`): `POST https://api.groq.com/openai/v1/chat/completions`, Bearer auth, `max_tokens=400`.
- **Gemini** (`gemini.py`): `POST https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent`, `x-goog-api-key` header, `maxOutputTokens=400`. Also `embed(texts)` for embeddings (UNTESTED ON TARGET).
- **base** (`base.py`): `Provider` ABC with `_call`, `complete`, `complete_with_tools` (not implemented — text TOOL/ANSWER protocol used instead). `PROVIDERS = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}`. `get_provider()` returns None if no provider configured or no key. `ask(prompt, timeout=8.0)` — requires `cloud_consent` and a provider; one retry, cached per prompt, 8s timeout. `api_key(provider)` reads from `.env` or environment. `mask(key)` shows `********` + last 4 chars. `set_key(provider, key)` writes to `.env` (git-ignored), never to database. `search_link(query)` builds a Google search URL.

Cloud consent: `config.get_bool("cloud_consent")` must be true and a provider + key must be configured for any LLM call. Without consent/key, `_llm_answer` returns `llm_blocked` or `llm_unavailable` replies; the agent returns a disabled message. Streaming (F01) is NOT implemented — replies are returned whole.

Voice (`adhyaksh/voice/`):
- **bridge** (`bridge.py`): `voice_input(theme_name, lang, speak_text, speak_nonce, key)` — declares a Streamlit component `adhyaksh_voice` from `adhyaksh/voice/component/`. Returns `{"text", "lang", "nonce"}` after a recognized utterance, else None. Never raises; failures fall back to typed input. UNTESTED ON TARGET.
- **component** (`component/index.html`): Web Speech API (`SpeechRecognition`/`webkitSpeechRecognition`) for input, `speechSynthesis` for output. Language select (en-IN, hi-IN, gu-IN). Status display. No wake word implemented in the current HTML. UNTESTED ON TARGET.
- The Chat page calls `bridge.voice_input` with `speak_text` set to the latest assistant reply when `voice_reply` is enabled and the reply is new. Spoken replies are not sentence-by-streaming-sentence; the full reply text is passed to synthesis.

Not supported yet: wake word ("Adhyaksh"/"Hey Adhyaksh"), follow-up window, barge-in, stop button, sentence-by-streaming-sentence spoken replies, voice persona, voice confirmations for L2 only.

## 9. Vision

Object Detection page (`pages/vision.py`) + `adhyaksh/vision/`:
- **detector** (`detector.py`): `detect(image_bytes, conf=0.4, imgsz=640, model_choice="balanced")` — lazy imports `ultralytics.YOLO`, loads and caches the model per choice. Model choices: `fast` = yolov8n.pt, `balanced` = yolov8s.pt, `accurate` = yolov8m.pt. Weights stored under `models/` (git-ignored). Rejects files > 10 MB and non-JPG/PNG/WEBP. Decodes bytes via `Image.open(io.BytesIO(...)).convert("RGB")`; unreadable images return "The image could not be read.". Passes PIL Image to `model.predict(img, conf=conf, imgsz=imgsz, verbose=False)`. Results cached by `sha1(bytes):conf:imgsz:model_choice`. Returns `[{"label", "confidence", "box"}]` or `[{"error": ...}]`.
- `detect_raw(image_bytes, model_choice, imgsz)` — top-5 detections at confidence 0.05, using the same imgsz as main detection. Cached separately.
- `average_brightness(image_bytes)` — PIL `ImageStat.Stat` on grayscale, returns 0-255 or None.
- `classify(image_bytes, imgsz=640)` — YOLOv8 classification fallback (`yolov8n-cls.pt`), cached. Returns top guesses `[{"label", "confidence"}]` or an error string.
- Model load failure: if download fails, falls back to weights already on disk; if neither works, returns a clear message ("Model load failed: ..." or "Object detection needs the ultralytics package...").
- **descriptions** (`descriptions.py`): `_DESCRIPTIONS` — two-sentence plain descriptions for all 80 COCO class names. `describe(label)` returns the description or a fallback. `_WIKI_TITLES` — label-to-title overrides for ambiguous labels (mouse→Computer mouse, remote→Remote control, cell phone→Mobile phone, tv→Television, dining table→Table (furniture), potted plant→Houseplant, sports ball→Ball). `wikipedia(label)` — `@st.cache_data(ttl=3600)` fetch of the first two sentences from `https://en.wikipedia.org/api/rest_v1/page/summary/{title}` (en.wikipedia.org only, 5s timeout, User-Agent header). Returns empty string on failure (offline or request fails — no error shown).

Page flow: model selector + image size slider + confidence slider. Camera and Upload tabs, each handled by a `render(key, file)` function with its own session-state cache keyed by `sha1:conf:imgsz:model_choice`. On detection: annotated image (PIL ImageDraw red boxes + labels), grouped detection list (name, count, best confidence %, description + Wikipedia). If empty: "No objects found. Try better light..." then classifier fallback "Closest match" top 3. Collapsible "Details" expander: size, file size, average brightness, model name, confidence threshold, camera bytes read (camera only), raw detections at 0.05 (top 5).

## 10. Config and settings

All settings in `adhyaksh/config.py`, `DEFAULTS` dict. Values stored in SQLite (`settings` table); `get(key)` returns the DB value or the default; `set_value(key, value)` writes to DB. Unknown keys raise `KeyError`.

| Key | Default | Meaning |
|-----|---------|---------|
| `theme` | `""` | `""` = never chosen (follow OS), else `"light"` or `"dark"` |
| `confidence_threshold` | `"0.60"` | Minimum confidence for intent prediction (tuned during training via `tune_tau`) |
| `conversation_turns` | `"8"` | Number of turns loaded for chat history |
| `active_model` | `""` | Active intent model ID (set by training or Model Lab) |
| `cloud_consent` | `"false"` | Allow sending questions/passages to the cloud LLM provider |
| `voice_reply` | `"false"` | Speak assistant replies aloud via browser voice |
| `llm_provider` | `""` | `""`, `"groq"`, or `"gemini"` |
| `allowed_folders` | JSON of `[default_workspace()]` | Allowed root folders for file operations |
| `default_work_folder` | `~/Documents/ADHYAKSH_Workspace` | Default workspace folder |
| `app_allowlist` | JSON of default apps | Application name → command list allow-list |
| `embedding_model` | `"gemini-embedding-001"` | Gemini embedding model (per Google docs, checked 2026-11-06) |
| `groq_model` | `"llama-3.1-8b-instant"` | Groq model (per Groq docs, checked 2026-11-06) |
| `gemini_model` | `"gemini-3.5-flash-lite"` | Gemini model (per Google docs, checked 2026-11-06) |
| `doc_min_score` | `"0.15"` | Minimum document match score for RAG retrieval |
| `power_mode` | `"false"` | Enable `run_python` tool (restricted sandbox, L2 confirmation every time) |
| `vision_model` | `"balanced"` | Object detection model: `fast`, `balanced`, `accurate` |
| `vision_imgsz` | `"640"` | Object detection image size: `640` or `960` |

Helper functions: `get_float(key)`, `get_bool(key)`, `get_allowed_roots()` (resolved Paths), `configure_folders(paths, default)` (validates no system paths, default inside a root, saves), `models_dir()`, `data_dir()`, `db_path()`, `uploads_dir()`, `logs_dir()`, `backups_dir()`, `default_workspace()`, `default_app_allowlist()` (OS-specific defaults), `default_special_folders()` (Windows: Recycle Bin, Downloads, Documents, Desktop, Explorer).

Settings page (`pages/settings.py`) exposes: folders, assistant (threshold, model, voice), language model (provider, key, model names, cloud_consent), power mode, apps allow-list JSON, your data (export/wipe).

## 11. Tests

Test files under `tests/` (no API key or network needed; HTTP calls monkeypatched; `ADHYAKSH_NO_OPEN=1` set to avoid opening apps):

- `test_chat.py` — engine end-to-end: identity cases, safe math, memory store, chat flows, file/office tools, apps and status, document Q&A, consent logic.
- `test_chat_regression.py` — 15 regression cases (date/time, bot identity, math, slots/file tools, apps/special folders/web, knowledge routing, name handling). 15/15 pass.
- `test_web_commands.py` — 139 tests for `parse_web_command` and end-to-end web commands (file vs web disambiguation, local search, Hindi/Gujarati, guard rails).
- `test_web_search.py` — 15 tests for `web_search` and `fetch_page` (DuckDuckGo/Wikipedia parsing, fallback, localhost/private IP blocking, timeout, HTTP errors, truncation, agent sources).
- `test_agent_injection.py` — 1 test: prompt injection via fetched page content must not trigger file_delete.
- `test_routing_fixes.py` — 11 routing/slot cases (folder/file slots, web open, name persistence, word-based math, small talk, unsupported).
- `test_modes.py` — 7 tests for Chat/Cowork mode: chat mode refuses file_create/app_open/screenshot/special_folder_open; chat mode answers math/identity/smalltalk; cowork mode creates files; default mode is cowork. Uses a temporary trained workspace.
- `test_boost.py` — 10 tests (8 pass, 2 skipped on Windows for symlink privilege): stats ranges, temp scan old/new/symlink, clean temp delete/keep/symlink/outside/empty-subfolders, default dir.
- `test_vision.py` — tests for `describe()` (5 labels + unknown), detection grouping/counts, corrupted image rejection, too-large/wrong-type rejection, missing ultralytics message, model choice respected, imgsz passed, classifier fallback top-3 format, detect_raw top-5, average brightness, Wikipedia summary + failure.
- `test_tools.py` — tool tests; has a pre-existing exit-15 teardown crash on Windows (baseline, not a failure). Run with `--ignore=tests/test_tools.py`.
- `test_dataset.py`, `test_db.py`, `test_data_admin.py`, `test_guard.py`, `test_logging.py`, `test_models.py`, `test_policy.py`, `test_rag.py`, `test_responses.py`, `test_static.py`, `test_theme.py` — supporting module tests.

Windows-only tests: `test_open_downloads_folder_real_path` in `test_routing_fixes.py` (skipped on non-Windows). Symlink tests in `test_boost.py` (skipped on Windows). Tests needing a real API key: none — all LLM tests use fake providers. Tests needing network: none — all HTTP is monkeypatched.

Full suite: run `.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_tools.py`. The `test_tools.py` teardown crash (exit 15) is pre-existing and baseline.

## 12. Known issues and conventions

Known issues:
- Stale Streamlit modules: after editing `adhyaksh/ui/theme.py` or other imported modules, a running Streamlit process keeps the old bytecode in memory. A full Streamlit restart (Ctrl+C, then `run.bat`/`run.sh`) is required for changes to take effect.
- New pages need an icon entry in `adhyaksh/ui/icons.py` (`PAGE_ICONS[slug]`), otherwise `app.py`'s `icons.page_icon(slug)` raises `KeyError`.
- `test_tools.py` has a pre-existing exit-15 teardown crash on Windows (baseline, not a test failure). Exclude with `--ignore=tests/test_tools.py`.
- Hindi/Gujarati reply templates are UNREVIEWED pending author review.
- M2 PyTorch MLP is UNTESTED ON TARGET.
- Dataset (`data/intents.csv`, `data/test_codemixed.csv`) is UNREVIEWED (generated, `reviewed=false`).
- `docs/RESULTS.md` not regenerated after the last retrain.
- `requirements-core.txt` has lower bounds only; `pip freeze` should be run after first install and pinned.
- Voice component (`adhyaksh/voice/`) is UNTESTED ON TARGET; wake word, follow-up window, barge-in, stop button, sentence-by-streaming-sentence replies, voice persona, and L2-only voice confirmations are not implemented.

Coding style:
- No emojis anywhere in code or strings.
- No `eval`/`exec` on user text (math uses `ast`-based `safe_eval`).
- No secrets in code or database; API keys in git-ignored `.env`; secrets redacted in logs (`logging_setup.py`).
- Expected failures return `Result` objects, never raise. `Result.failure(error_code, message)`.
- All file actions go through `safety.policy.run_guarded` (L0-L3, allowed folders, confirmation, audit).
- Every action attempt writes exactly one audit row (append-only, SQLite triggers prevent update/delete).
- Reply templates in `responses.py` with EN/HI/GU variants; `t(key, lang, **kwargs)` falls back to English.
- Type hints used throughout (`from __future__ import annotations`).

How to add a new page:
1. Create `pages/<slug>.py` calling `ui.page_header(...)` and `theme.inject(...)`.
2. Add `("<slug>", "Title")` to `PAGES` in `app.py`.
3. Add `"<slug>": ":material/icon:"` to `PAGE_ICONS` in `adhyaksh/ui/icons.py`.

How to add a new intent:
1. Add the intent string to `dataset.INTENTS` in `adhyaksh/nlu/dataset.py`.
2. Add templates in `TEMPLATES` in the same file (en/hi/gu/hinglish/gujlish).
3. Add handling in `engine._dispatch` and/or `router.match_rules`.
4. Retrain: `python -m adhyaksh.nlu.train --all`.

How to add a new tool:
1. Implement the function in `adhyaksh/tools/<module>.py` going through `policy.run_guarded`.
2. Register it in `adhyaksh/agent/registry.py` with name, JSON schema, level, and callable.
3. Add the level to `policy.LEVELS` and PATH_ACTIONS if applicable.
4. Handle the intent in `engine._dispatch` (or let the agent use it).

## 13. Roadmap

Planned items (from project documentation):
- Voice page — dedicated voice interface page (currently voice is only integrated into Chat via `bridge.voice_input`).
- Evaluation dashboard — view training/evaluation results in the UI.
- Retrain from corrections — automatically incorporate "Wrong intent?" feedback (`feedback` table) into training data.
- OCR — optical character recognition for scanned documents in the Documents page.
- Reminders — scheduled reminders based on remembered facts.
- Study tools — learning/review features using memory facts.
- RAM-process and kill commands — list and terminate running processes (would be a new tool, likely L2).
- Wake word ("Adhyaksh"/"Hey Adhyaksh"), follow-up window (10s), barge-in, stop button for voice.
- Sentence-by-streaming-sentence spoken replies in reply language.
- Voice persona (short, calm, conversational answers).
- Voice confirmations (confirm/yes/cancel/no) for L2 only, never for L3 or Power mode.
- Manual test script in `docs/QA_LOG.md` for wake word, follow-up window, barge-in, each language.

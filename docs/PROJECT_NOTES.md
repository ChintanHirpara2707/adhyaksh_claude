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

See [docs/FILES.md](./docs/FILES.md) for the complete folder and file listing. The project root contains `app.py`, `run.bat`, `run.sh`, `pytest.ini`, `.env` (git-ignored), `.gitignore`, source files (`CHANGELOG.md`, `README.md`, `requirements-core.txt`, `requirements-optional.txt`), and the `pages/`, `adhyaksh/`, `tests/`, `data/`, `models/`, `docs/` directories.

## 3. Pages and features

Each page file calls `ui.page_header(title, description)` and `theme.inject(config.get("theme") or "light")`.

- **Chat** (`pages/chat.py`): Type or speak a command. Shows message history with streaming for agent replies. "Wrong intent?" correction button per assistant reply (writes to `feedback` table). Voice input via `bridge.voice_input` (speak replies aloud if `voice_reply` enabled). Mode toggle (Chat/Cowork) stored in `st.session_state["mode"]`, passed to `engine.handle_message(..., mode=mode)`. When the engine returns `suggest_mode == "cowork"`, shows a "Switch to Cowork" button. Calls `engine.handle_message`, `engine.confirm`, `context.history`, `context.get`, `bridge.voice_input`, `dataset.INTENTS`.
- **Cowork**: Not a separate page; it is a mode (`mode="cowork"`) on the Chat page. In Cowork mode all OS_INTENTS (file/app/system tools) are allowed. In Chat mode they are refused with a `needs_cowork` reply and a "Switch to Cowork" button.
- **Voice**: Built into Chat via `adhyaksh/voice/bridge.py` and `adhyaksh/voice/component/index.html` (Web Speech API recognition + synthesis, wake word not implemented in the current HTML). Untested on target.
- **Chat attachments** (`pages/chat.py`, replaces the removed Documents page): attach PDF/DOCX/TXT (up to 25 MB each), index them, list indexed documents, remove documents, ask questions with cited sources. Calls `loader.ingest_bytes`, `loader.list_documents`, `loader.delete_document`, `answerer.answer`, `retriever.embedding_mode`.
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

SQLite schema detail: see [docs/DATABASE.md](./docs/DATABASE.md) for every table and column (`profile`, `settings`, `conversations`, `messages`, `memory_facts`, `documents`, `doc_chunks`, `audit_log`, `model_registry`, `eval_runs`, `feedback`). `db.py` also provides: `connect()` context manager (WAL journal, foreign_keys=ON), `schema_version()`, `init()` (runs migrations), `execute()`, `executemany()`, `query_all()`, `query_one()`, `get_setting()`, `set_setting()`, `backup()`, `restore()`, `export_bytes()`, `wipe()`, `utcnow()`.

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

See [docs/CONFIG.md](./docs/CONFIG.md) for the complete settings reference. All settings in `adhyaksh/config.py`, `DEFAULTS` dict. Values stored in SQLite (`settings` table); `get(key)` returns the DB value or the default; `set_value(key, value)` writes to DB. Unknown keys raise `KeyError`. Settings page (`pages/settings.py`) exposes: folders, assistant (threshold, model, voice), language model (provider, key, model names, cloud_consent), power mode, apps allow-list JSON, your data (export/wipe).

## 11. Tests

See [docs/TESTS.md](./docs/TESTS.md) for the complete test reference. Test files under `tests/` (no API key or network needed; HTTP calls monkeypatched; `ADHYAKSH_NO_OPEN=1` set to avoid opening apps).

## 12. Rules for agents

- Run only tests for the changed file; do not run the full test suite.
- Never launch Chrome, WhatsApp, or any other app.
- Never push to GitHub unless asked.
- No emojis anywhere in code or strings.
- One small task at a time.
- Restart Streamlit fully after changing imported modules (stale bytecode).
- New pages need an entry in `ui/icons.py` (`PAGE_ICONS[slug]`).

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

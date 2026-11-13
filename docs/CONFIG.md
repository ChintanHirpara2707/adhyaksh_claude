# Config — Settings reference

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

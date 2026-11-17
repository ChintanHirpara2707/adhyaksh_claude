# ADHYAKSH

A private, local-first desktop assistant for Windows that understands English, Hindi, Gujarati and code-mixed
Hinglish and Gujlish. It works with files, applications, system information, memory, documents (notebooks with
cited answers), reminders, the clipboard, voice and images. It runs fully offline. A cloud language model (Groq or Gemini)
is used only if you add a key and allow cloud use. A local model through Ollama needs neither.

Built with Streamlit, scikit-learn intent models, SQLite and a safety gateway that checks and logs every action.

## Features

| Area | What it does |
|---|---|
| Chat | Commands and questions in five language styles; rules first, then a trained intent model, then an optional language model with tool calling |
| Files and apps | Create, read, write, list, rename and delete files inside allowed folders; open and close allow-listed applications |
| Memory | "Remember that my car is an Audi", then "what is my car" |
| Notebooks | Attach PDF, DOCX or text files; answers cite their sources; per-source summaries and removal |
| Cowork | Running programs and their memory use, ending a program (with confirmation), reminders, clipboard, multi-step requests |
| Voice | Browser or fully local speech-to-text (faster-whisper), wake word, barge-in, spoken confirmations |
| Vision | Object detection with positions, sizes and colours; reading text in photos and on the screen (offline OCR) |
| PC Performance | CPU, RAM and disk use; cleaning old temp files (with confirmation) |
| Health | Every dependency, model file, setting and service with its state |

## Requirements

- Windows 10 or 11 (primary target; most features also run on macOS and Linux)
- Python 3.11 or 3.12
- About 1.5 GB of free disk for the required packages; optional models need more (see below)

## Install

Double-click `run.bat`. On first start it creates a virtual environment, installs `requirements-core.txt` and
starts the app.

By hand:

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements-core.txt
```

Optional parts (each is listed with its size in `requirements-optional.txt`; install only what you need):

| Package | Enables | Packages | Model download |
|---|---|---|---|
| torch (CPU build) | the MLP intent model | about 550 MB | none |
| ultralytics | object detection | about 10 MB, plus OpenCV and other dependencies | 6 to 50 MB per detector, on first use |
| fastembed | multilingual document search | about 28 MB | about 240 MB, from Settings |
| faster-whisper | local speech-to-text | about 140 MB | 75 to 480 MB, from Settings |
| rapidocr_onnxruntime | reading text in images | about 24 MB | none (models included) |

No model is ever downloaded unless you press the download button or use the feature that needs it.

## Run

```bash
streamlit run app.py
```

Then open http://localhost:8501. On the first visit, choose the folders ADHYAKSH may work in.

## Train the intent models

```bash
python -m adhyaksh.nlu.dataset validate
python -m adhyaksh.nlu.train --all
```

Training takes about three minutes on a laptop CPU and rewrites `docs/RESULTS.md`. The Model Lab page can also
retrain and switch models.

## Tests

```bash
python -m pytest tests -q --ignore=tests/test_tools.py
```

```bash
python tests/eval/run_eval.py
```

```bash
python tests/eval/run_real_eval.py --label "my run"
```

The first command runs the unit tests (no network or API key needed). The second is the 399-case regression suite,
and the third is the 238 held-out real commands (results in `docs/REAL_EVAL.md`). GitHub Actions
(`.github/workflows/ci.yml`) runs all three on Windows with Python 3.11 and 3.12.

## Health

The Health page lists every required and optional package with its version, every model file, the database,
free disk space, the language model provider (a key is shown only as present or absent), and any invalid setting.
It also shows recent warnings and errors from the log.

Logs are JSON lines in `data/logs/adhyaksh.jsonl`, one event per line (tool actions, chat messages without their
text, network retries, errors with details). Anything that looks like an API key is removed before it is written.

## Packaging (Windows)

```bash
pip install pyinstaller
pyinstaller packaging/adhyaksh.spec --noconfirm
```

This builds `dist/ADHYAKSH/ADHYAKSH.exe`. Starting it opens the app in the browser. The database, logs and
downloaded models are kept in `data` and `models` next to the program. The `.env` file is never included.

## Privacy and safety

- Everything runs on this computer by default. Cloud use is off until you allow it in Settings.
- API keys go in `.env` (copy `.env.example`) or in Settings, and are never stored in the database or written to logs.
- Actions have four levels: L0 read-only, L1 reversible, L2 destructive (needs your confirmation), L3 blocked. File
  actions are limited to the allowed folders, and system folders are never allowed. Every attempt is written to the
  audit log (Activity page).
- Only allow-listed applications can be opened. No user text is ever run as code.

## Project layout

| Folder | Contents |
|---|---|
| `app.py`, `pages/` | Streamlit entry point and pages (pages call only `adhyaksh.services` and `adhyaksh.ui`) |
| `adhyaksh/services/` | One service module per page: the functions that page may use |
| `adhyaksh/chat/`, `adhyaksh/agent/` | Message handling, rules, the tool-calling agent |
| `adhyaksh/nlu/` | Training data generator, intent models, evaluation |
| `adhyaksh/tools/`, `adhyaksh/safety/` | Tool actions and the safety gateway with audit log |
| `adhyaksh/rag/`, `adhyaksh/memory/` | Notebooks and document search; personal memory |
| `adhyaksh/voice/`, `adhyaksh/vision/` | Speech and the browser voice control; detection, scene description, OCR |
| `adhyaksh/llm/`, `adhyaksh/net.py` | Language model providers; HTTP with timeouts and retries |
| `tests/` | Unit tests, regression and real-command evals |
| `docs/` | Notes, results, the upgrade log (`docs/UPGRADE_LOG.md`) and design documents |
| `packaging/` | PyInstaller spec and launcher |

## Known limitations

See `docs/PROGRESS.md` and the "Must be tested by hand on Windows" list in `docs/UPGRADE_LOG.md`.

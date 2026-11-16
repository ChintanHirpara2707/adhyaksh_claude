# ADHYAKSH roadmap: production-grade upgrade

Branch: `master-upgrade`. Progress and scores are recorded in docs/UPGRADE_LOG.md. Never push; commit after every phase.

## How progress is measured

- **Real-world test set:** `data/test_real.csv`, 238 hand-written commands in five language styles (English, Hindi, Gujarati, Hinglish, Gujlish), one group per product feature. It is a held-out measure: none of its sentences may be added to `data/intents.csv`.
- **Eval script:** `python tests/eval/run_real_eval.py --label "<phase>"`. It trains a fresh model set in a temporary folder, runs every command through `engine.handle_message` with all tools mocked and no network, writes `docs/REAL_EVAL.md` and appends a row to `tests/eval/real_history.csv`.
- **What it measures:** the offline path (rules and the trained classifier). The language-model agent path cannot be scored without a real model; it is covered by unit tests with a scripted fake model.
- **Rule:** after each phase the eval is re-run. A change that lowers the overall pass rate, or any feature that already met its target, is reverted or fixed before the phase is committed.
- **Regression suite:** `python tests/eval/run_eval.py` (399 older cases) must stay at or above 398 of 399.

## Feature targets (pass rate on data/test_real.csv, offline path)

| Feature | Baseline (P0) | Target | Phase that owns it |
|---|---|---|---|
| chat | 70.3% (26/37) | 90% | P1 |
| memory | 85.0% (17/20) | 90% | P1 |
| files | 68.8% (22/32) | 90% | P1 |
| apps | 86.4% (19/22) | 90% | P1 |
| system | 93.3% (14/15) | 90% | P1 (keep) |
| safety (unsupported requests never run a tool) | 53.8% (7/13) | 100% | P1 |
| notebook | 55.0% (11/20) | 85% | P2 |
| voice | 100% (12/12) | 90% | P3 (keep) |
| processes | 0% (0/16) | 85% | P4 |
| reminders | 0% (0/20) | 85% | P4 |
| clipboard | 0% (0/9) | 85% | P4 |
| multi-step | 0% (0/10) | 70% | P4 |
| vision | 50.0% (6/12) | 85% | P5 |
| **all** | **56.3% (134/238)** | **88%** | |

## Phases

### P0 Baseline (done when the baseline row is in the log)
- `data/test_real.csv`, `tests/eval/run_real_eval.py`, `docs/REAL_EVAL.md`, baseline recorded.

### P1 Core agent and correctness fixes
- Native tool calling for Groq (OpenAI-style `tools`), Gemini (`functionDeclarations`) and Ollama (`/api/chat` tools), one provider interface `chat(messages, tools)`.
- Agent loop uses native calls; every tool goes through `safety.policy.run_guarded`; L2 pauses for confirmation; tool output is data, never instructions.
- When a model is available (local, or cloud with consent) the agent answers; rules and the classifier are the offline fallback. Confirmations and pending questions stay deterministic.
- Fixes: file and folder names taken from command words; `default_work_folder` ignored; memory recall and attachment questions mis-routed; model claiming actions it did not do (claims are checked against executed tool steps); `app_close` must always ask for confirmation.
- Acceptance: unit tests for each fix and for the agent loop with a fake model for all three providers' wire formats; chat, memory, files, apps, system and safety meet their targets; regression suite holds.

### P2 Notebook-style sources
- Notebooks (named collections of sources) with per-notebook indexes; per-source delete; source list; summaries; answers with citations (file, page or section).
- Real embeddings when a light local model is available (fastembed or sentence-transformers if installed), TF-IDF otherwise; Gemini embeddings only with consent.
- Acceptance: notebook feature at 85%; tests for per-notebook isolation, citation format, delete and summary.

### P3 Voice
- Local speech-to-text with faster-whisper (optional dependency, small model), browser recognition as fallback; better text-to-speech (voice choice, rate; local engine if installed); wake word; barge-in (stop speaking when the user talks); spoken confirmations for L2 actions.
- Acceptance: voice feature stays at 90% or more; tests for the audio pipeline with a fake transcriber, barge-in logic and spoken confirmation flow. Real microphone testing is manual on Windows.

### P4 Cowork
- Process monitor and top RAM list, kill with confirmation (L2, protected system processes refused), reminders and scheduling (one-shot, relative, daily) stored in SQLite, clipboard read and write, multi-step tasks offline (split on "and then") and through the agent.
- Acceptance: processes, reminders, clipboard at 85%, multi-step at 70%; tests for the scheduler, kill safety and clipboard.

### P5 Vision
- OCR (text in images), more objects (tiled and open-vocabulary modes surfaced in chat), richer descriptions (counts, positions, sizes, dominant colours).
- Acceptance: vision feature at 85%; tests with fake OCR and detector.

### P6 Engineering quality
- Service layer separate from Streamlit pages, structured logging (JSON lines), clear error messages for every failure, retry and timeout on every network call, config validation, health check page, GitHub Actions CI, Windows packaging with PyInstaller, full README.
- Acceptance: pages import only services; a test that fails if a page imports tools directly; CI workflow file; health page lists every dependency and its state.

### P7 UI polish and architecture note
- Desktop layout polish; `docs/ARCHITECTURE_FASTAPI.md` with a written recommendation on moving to FastAPI plus a web front end.

## Standing constraints
- Free and light tools only; the disk size of every new dependency is recorded in docs/UPGRADE_LOG.md.
- Cloud language models only behind `cloud_consent`. Never touch `.env`; never print keys.
- No emojis. No full-suite pytest and no app launching during development: only tests for changed files plus the eval.

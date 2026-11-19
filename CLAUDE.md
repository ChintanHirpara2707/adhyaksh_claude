# CLAUDE.md

Goal: ADHYAKSH is a private, local-first, multilingual (English, Hindi, Gujarati, Hinglish, Gujlish) assistant for a Windows laptop. It understands typed or spoken commands and safely controls files, apps, processes, reminders, clipboard and system status; answers from notebook sources with citations; remembers facts; reads text and objects in images; and uses an optional language model (Ollama local, or Groq/Gemini with consent) for open questions.

Stack: Streamlit UI (pages/ call adhyaksh/services/, never tools directly), Python 3.11/3.12, SQLite, scikit-learn intent models (TF-IDF + LogReg, calibrated SVM; PyTorch MLP untested on target), rule layer plus native tool-calling agent, YOLOv8 vision, optional local faster-whisper, fastembed and rapidocr (see requirements-optional.txt).

## Run, test, train
- Run: `.\run.bat` (Windows) or `./run.sh`; starts `streamlit run app.py`.
- Test (changed files only): `.venv\Scripts\python.exe -m pytest tests\test_<name>.py -q`.
- Full suite and both evals: once at the end of a phase only: `python -m pytest tests -q --ignore=tests/test_tools.py`, `python tests/eval/run_eval.py` (must stay at least 398/399), `python tests/eval/run_real_eval.py --label "<phase>"` (must not drop).
- Train: `python -m adhyaksh.nlu.dataset validate`, then `python -m adhyaksh.nlu.train --all` (rewrites docs/RESULTS.md).

## Map (one line per area)
- `app.py` entry and navigation; sidebar groups come from `adhyaksh/services/shell.py`.
- `pages/` chat, memory, tools, vision, performance, model_lab, activity, health, settings.
- `adhyaksh/services/` the only layer pages may call; wraps chat, memory, tools, settings, health.
- `adhyaksh/chat/` engine.handle_message (mode chat or cowork), router (rules and slot extractors), identity, context.
- `adhyaksh/agent/` native.py tool-calling loop, registry.py tools; runner.py is the old text protocol.
- `adhyaksh/llm/` providers groq, gemini, ollama, wiki fallback; consent-gated; calls go through net.py.
- `adhyaksh/nlu/` dataset, features, models, train, evaluate, registry (MIN_GAP rejection).
- `adhyaksh/tools/` files, office, apps, processes, reminders, clipboard, system, boost, features, when.
- `adhyaksh/safety/` policy (levels L0 read, L1 reversible, L2 destructive needs confirmation, L3 blocked), confirm, audit.
- `adhyaksh/rag/` notebook sources: loader, chunker, embedder, retriever, answerer, sources.
- `adhyaksh/memory/`, `adhyaksh/vision/`, `adhyaksh/voice/` (bridge, speech, stt, browser component).
- `tests/` pytest; `tests/eval/` regression and real-world evals; `data/test_real.csv` 238 hand-written commands.
- `packaging/` PyInstaller spec; `.github/workflows/ci.yml`; `docs/` all detail.

## Rules for agents
- Never print keys or .env values; keys live only in the git-ignored `.env`. Cloud use needs the `cloud_consent` setting.
- Every OS action goes through `safety.policy.run_guarded`; never weaken a level without being asked. Closing apps has no confirmation (requested); delete and process end keep L2.
- Never launch Chrome, WhatsApp or other apps in tests; mock OS calls. Never push to GitHub unless asked; work on a branch and commit.
- No emojis anywhere. No eval/exec on user text. Expected failures return `Result`, never raise.
- One small task at a time. After a change that lowers either eval, revert it.
- Restart Streamlit fully after changing any imported module; a new page needs an entry in `services/shell.py` and an icon in `adhyaksh/ui/icons.py`.
- Keep disk light: record the size of any new dependency; model files go in `models/` (git-ignored; override with ADHYAKSH_MODELS_DIR).

## Status
Branch history: P0 to P7 done and merged to main (agent with native tool calling, notebooks, local voice, Cowork tools, OCR and vision, service layer, Health page, CI, packaging). Real eval 237/238 offline (tuned by the same agent, so optimistic).
Untested on the Windows target: agent with a real model, local speech recognition, wake word, PDF loading, process end, reminders, PyInstaller build, CI. Hand-test list: docs/UPGRADE_LOG.md.
Next: docs/JARVIS_PLAN.md (branch jarvis-upgrade): Phase 1 universal brain and NLU, Phase 2 autonomy and OS tools, Phase 3 background engine, voice and HUD. One phase at a time; stop for approval after each.

Details (read only when needed): docs/PROJECT_NOTES.md, FILES.md, CONFIG.md, DATABASE.md, TESTS.md, ROADMAP.md, UPGRADE_LOG.md, JARVIS_PLAN.md.
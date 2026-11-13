# CLAUDE.md

Goal: A private, local-first, multilingual (English/Hindi/Gujarati/Hinglish/Gujlish) desktop assistant for file, app, system, memory, document Q&A, and optional cloud LLM tasks on a Windows laptop.

Stack: Streamlit UI, Python 3.11/3.12, scikit-learn TF-IDF intent models (M1 logreg, M3 SVM; M2 PyTorch untested), SQLite database, Groq/Gemini LLM providers (consent-gated), psutil/Pillow/send2trash tools, Ultralytics YOLOv8 object detection (optional).

How to run / test / train:
- Run: `.\run.bat` (Windows) or `./run.sh`; creates `.venv`, installs `requirements-core.txt`, starts `streamlit run app.py`.
- Test: `.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_tools.py` (test_tools.py has a pre-existing teardown crash).
- Train: `python -m adhyaksh.nlu.train --all`; rewrites `docs/RESULTS.md`.

Folder map (1 line per folder):
- `pages/` — Streamlit pages (chat, memory, tools, model_lab, activity, settings, vision, performance)
- `adhyaksh/` — package: chat engine, NLU models, RAG, tools, safety, UI, voice, vision, LLM providers
- `tests/` — pytest suite (no API key or network needed)
- `data/` — intents.csv, test_author.csv, test_codemixed.csv, adhyaksh.db (git-ignored)
- `models/` — trained intent models and YOLOv8 weights (git-ignored except .gitkeep)
- `docs/` — PROJECT_NOTES.md, PROGRESS.md, RESULTS.md, CONFIG.md, TESTS.md, FILES.md, DATABASE.md

Rules: never hardcode API keys (use `.env`); cloud use is consent-based (`cloud_consent` setting); no emojis; no eval/exec on user text; run only tests for the changed file; never launch apps (Chrome, WhatsApp); never push to GitHub unless asked; one small task at a time; restart Streamlit fully after changing imported modules; new pages need an icon in `adhyaksh/ui/icons.py`.

Current status: v0.7.0. Done: P0-P7 phases, A1-A5 agent features, voice integrated into chat, object detection page, PC performance page, Chat/Cowork mode, safety gateway with L0-L3 levels and audit log. Untested on target: voice component, PyTorch MLP (M2), PDF loading, send2trash, keyed Groq/Gemini calls, Windows app launching, clean install.

Current focus / next 5 tasks:
1. Regenerate docs/RESULTS.md after last retrain.
2. Review data/intents.csv and data/test_codemixed.csv (still UNREVIEWED).
3. Pin requirements-core.txt with pip freeze.
4. Test PC Performance page on target.
5. Test voice integration on target.

Details: docs/PROJECT_NOTES.md (read only when needed)

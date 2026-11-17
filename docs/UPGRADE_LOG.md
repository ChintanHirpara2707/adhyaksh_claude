# Upgrade log

How to resume in a new session: read docs/ROADMAP.md, then the last entry here. Branch `master-upgrade`. Measure with
`python tests/eval/run_real_eval.py --label "<phase>"` (about 2 minutes) and keep `python tests/eval/run_eval.py` at 398 of 399 or better.
Commit after every phase with explicit paths (the working tree has unrelated deleted files that must not be committed). Never push.

| Phase | Change | Score before | Score after | Next step |
|---|---|---|---|---|
| P0 | Wrote data/test_real.csv (238 commands, 13 features, 5 language styles), tests/eval/run_real_eval.py, docs/ROADMAP.md; eval mocks now record tool arguments (`arg:` and `notool` checks) | none | 134/238 = 56.3% (chat 26/37, memory 17/20, files 22/32, apps 19/22, system 14/15, processes 0/16, reminders 0/20, clipboard 0/9, notebook 11/20, voice 12/12, vision 6/12, multi-step 0/10, safety 7/13) | P1: native tool-calling agent and the five listed fixes |
| P1 | Native tool calling for Groq, Gemini and Ollama (`Provider.chat`, `llm.chat`), new agent loop `adhyaksh/agent/native.py` behind `run_guarded` with confirmation pause/resume, Chat-mode tool filter, honesty guard (`guard_claims`), agent-first routing with offline fallback, 7 new agent tools, `agent_mode` setting. Offline fixes: requests no longer read as names, multi-word file names, content and folder-name extraction, memory-first and document-first answers, attachment "not found" reply, unsupported device requests refused, pending file-name answers cleaned. Verified (not reproduced as bugs): `default_work_folder` is honoured and `app_close` always asks for confirmation; tests now lock both in | 134/238 = 56.3% | 165/238 = 69.3% (chat 35/37, memory 19/20, files 32/32, apps 22/22, system 15/15, safety 13/13, voice 12/12; notebook 11/20, vision 6/12, processes/reminders/clipboard/multi-step 0). Regression suite 398/399 | P2: notebooks (per-notebook index, embeddings, citations, summaries, per-source delete); new intents source_list, source_delete, source_summary |
| P2 | Notebooks: schema v2 (`notebooks` table, `documents.notebook_id`, `documents.summary`), `adhyaksh/rag/sources.py` (notebooks, list, per-source delete with L2 confirmation, summaries), per-notebook retrieval, numbered citations with a source list, extractive summary stored at indexing, model-written summary when a model is usable. Real local embeddings: `adhyaksh/rag/embedder.py` with fastembed and paraphrase-multilingual-MiniLM-L12-v2 (never downloads by itself; Settings button). New intents source_list, source_summary, source_delete (rules, 317 training rows, agent tools, notebook_list and notebook_open tools). Chat page notebook picker and source list with summaries. Fixed a stale TF-IDF index cache. Regression suite: 5 summary cases now expect source_summary | 165/238 = 69.3% | 176/238 = 73.9% (notebook 11/20 -> 20/20; chat 37/37, files 32/32, apps 22/22, system 15/15, safety 13/13, voice 12/12, memory 19/20; vision 6/12; processes, reminders, clipboard, multi-step 0). Regression suite 398/399 | P3: voice (faster-whisper local speech-to-text, better text-to-speech, wake word, barge-in, spoken confirmations). Before that, retrain the installed models once: `python -m adhyaksh.nlu.train --all` (the training file gained 3 intents; not run here because docs/RESULTS.md has uncommitted local edits) |

## New dependencies and disk size

| Phase | Dependency | Required or optional | Disk size | Note |
|---|---|---|---|---|
| P0 | none | | | |
| P2 | fastembed 0.9.1 (with tokenizers, huggingface-hub, hf-xet, loguru, mmh3, py-rust-stemmers, tqdm) | optional | 28 MB of packages (measured) | Listed in requirements-optional.txt. onnxruntime was already installed |
| P2 | Embedding model paraphrase-multilingual-MiniLM-L12-v2 (ONNX, quantised) | optional | 241 MB in models/embeddings (measured, git-ignored) | Downloaded only from the Settings button; already downloaded on this machine during P2 |
| P1 | none (uses requests, already installed) | | 0 | Ollama itself is a separate optional program; models are about 2 GB or more |

## Must be tested by hand on Windows

- P1: the agent with a real model. Set a provider in Settings (Ollama local, or Groq/Gemini with a key and consent), then try: "create plan.txt with hello", "close notepad" (must show a confirmation), "what is in my memory", "stop listening". Check that a model which does not support tools gives a clear message and the app falls back to rules. Nothing in P1 was run against a real model.
- P1: Settings page checkbox "Let the language model use tools (agent)".
- P2: Chat page notebook picker: create a notebook, attach a PDF and a DOCX, ask a question (answer must show [1] and a Sources list), switch notebooks and confirm the other notebook's files are not used.
- P2: "summarize all my sources", "which sources have i added", "remove the source <name>" (must ask for confirmation).
- P2: Settings, Document search: the method should read "local multilingual embeddings" on this machine; on a clean install check the download button. Re-attach old documents to give them embeddings (old ones keep keyword search).
- P2: PDF text extraction with a real PDF (still never tested on the target).
- P2: retrain once with `python -m adhyaksh.nlu.train --all` so the installed classifier knows the three new source intents.

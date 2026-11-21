# Decisions

One file for the project brief, the decisions and assumptions, the open questions and the ideas kept out of scope.
Before 2026-11-21 these were five files (PROJECT_BRIEF.md, DECISIONS.md, ASSUMPTIONS.md, OPEN_QUESTIONS.md,
IDEAS.md); their text is kept here unchanged, with a dated note where something has since changed.

## Project brief

ADHYAKSH: a private, local-first, multilingual (English, Hindi, Gujarati, Hinglish, Gujlish) desktop assistant. Python + Streamlit + SQLite. Windows 10/11 primary.

Constraints: free tools only; footprint about 1.5 GB or less; CPU only; limited AI tokens; no emojis anywhere; professional replies from adhyaksh/responses.py.

Core: intent classifier (TF-IDF + Logistic Regression, calibrated linear SVM, PyTorch MLP), rule layer before the model, out_of_scope rejection, personal memory, document Q&A (RAG) with citations, file and folder tools, Excel/Word tools, app launcher with allow-list, web open, screenshot, voice input, Light/Dark theme.

Safety: every tool call goes through safety.authorize. L0 read-only, L1 reversible, L2 destructive (needs confirmation), L3 blocked. Allowed folders only. Audit log. No eval or exec on user text. Cloud use of documents is off by default. Text from files and web pages is data, never instructions.

Rules: small targeted edits, one task at a time, run pytest after each task, never train on data/test_author.csv, report real numbers only, mark anything not run as NOT RUN.

Current work: agent mode (LLM tool calling, like Claude Code) and JARVIS-style voice. (2026-11-21: both done; see docs/JARVIS_PLAN.md and docs/UPGRADE_LOG.md.)

## Decisions

- D-01 Tier A scope confirmed, Tier B deferred.
- D-02 Windows 11, Python 3.11 assumed.
- D-03 Single operator, no accounts.
- D-04 No API key; degraded mode first, LLM code kept ready.
- D-05 No embedding model; M3 is TF-IDF plus calibrated linear SVM.
- D-06 Assume 3 GB free disk.
- D-07 Author reviews Hindi and Gujarati data; generated rows marked UNREVIEWED.
- A-01 Added adhyaksh/result.py (Result object and error codes); needed by every service, not in the Section 6 tree.
- A-02 audit_log is append-only through SQLite triggers (UPDATE and DELETE abort). "Delete all my data" deletes the database file.
- A-03 audit_log.confirmed stores text: none, confirmed or cancelled.
- A-04 Exactly one audit row per final outcome (ran, failed, blocked, rejected, cancelled). A pending confirmation writes no row.
- A-05 All tool actions go through safety.policy.run_guarded; authorize() stays a pure function returning Decision.
- A-06 Theme choice persists in the SQLite settings table (single operator), not in the URL. First visit with no saved choice follows the OS preference through CSS only.
- A-07 Primary buttons use accent_strong (#A8502F) because white on the specified accent #C96442 is 3.9:1, below WCAG AA 4.5:1. The specified accent stays for focus rings and the active-navigation marker.
- A-08 Activity and Settings pages use st.table, not st.dataframe, because the dataframe canvas ignores CSS and would leak light colors in dark mode. (2026-11-21: Phase 4f gives Streamlit's own widgets, dataframes included, the same light and dark colours through .streamlit/config.toml.)
- A-09 Navigation uses st.navigation(position="hidden") plus sidebar page links so the theme switch sits above the links.
- A-10 TF-IDF retrieval stores no vector blobs (vectors depend on the whole corpus); doc_chunks.embedding is filled only in Gemini mode. Index is rebuilt in memory and cached.
- A-11 LLM model defaults follow provider documentation checked 2026-11-06 (groq llama-3.1-8b-instant, gemini gemini-3.5-flash-lite, embedding gemini-embedding-001). All three are editable in Settings because names change.
- A-12 LLM streaming (F01) is not implemented; replies are returned whole. (2026-11-21: implemented in Phase 4a for Groq, Gemini, Ollama and OpenAI-compatible servers, with a fallback to whole replies.)
- A-13 A recognised voice utterance is processed immediately like a typed message (Streamlit cannot fill the chat input programmatically).
- A-14 Model selection and tau tuning use the validation split only. The test split and the code-mixed file are used for reporting.
- A-15 API keys are stored only in the git-ignored .env file or environment, never in the database.
- A-16 Without send2trash the delete tool moves files to data/trash_fallback (used in the sandbox); on the target send2trash sends them to the Recycle Bin.
- A-17 Closing an application ends processes this program launched, and on Windows also processes with the allow-listed executable name.
- A-18 The rule layer also handles referential commands such as "delete it" so they resolve to the last file deterministically.

## Assumptions

- 2026-11-06: D-02, D-04 and D-06 were left as placeholders; defaults applied (Windows 11, Python 3.11, no key, 3 GB free).
- 2026-11-06: Streamlit 1.46 or newer is required for st.navigation(position="hidden"). Exact version is pinned after first install.
- 2026-11-06: The user profile root folder itself is treated as a system path (L3); folders inside it, such as Documents, are allowed when listed as allowed roots.
- 2026-11-06: Dark-mode switch is a labelled toggle ("Dark mode") instead of sun and moon icons, for reliable keyboard and screen-reader labels in Streamlit.

## Open questions

None.

## Ideas (out of scope)

- Stream LLM replies token by token (needs live key to test). (2026-11-21: done in Phase 4a; not yet tried with a live key.)
- Tier B: reminders, tasks, OCR, CSV analyzer, explainability, active learning, chat export, analytics, PIN lock. (2026-11-21: reminders done in P4, OCR in P5.)
- Hindi and Gujarati dataset review workflow inside the Model Lab (mark rows reviewed).

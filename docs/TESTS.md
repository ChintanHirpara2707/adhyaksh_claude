# Tests — Test suite reference

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

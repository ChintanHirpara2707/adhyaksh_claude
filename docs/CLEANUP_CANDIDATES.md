# Cleanup candidates (for review; nothing here has been deleted)

Found on 2026-11-21 by parsing every Python file under adhyaksh/, app_pages/ and hud/ and searching the whole
repository (code, tests, CI, packaging, scripts) for each name. "No caller" means the name appears only in its own
definition. A dynamic use (a name built from a string, a decorator registry, a page script loaded by path) cannot be
seen this way, so check each item before removing it. Every module under adhyaksh/, app_pages/ and hud/ is imported
or run somewhere; no whole module is unused.

## Functions with no caller

| Function | Note |
|---|---|
| `adhyaksh.agent.registry.list_tools` | The agent uses `registry.schemas()`; this helper is never called. |
| `adhyaksh.nlu.entities.has_file_extension` | A one-line wrapper of `find_file`; the router uses its own `_has_file_extension`. |
| `adhyaksh.nlu.entities.find_url` | The router uses `extract_url` / `extract_web_url`, and frames use the `entities._URL` pattern directly. |
| `adhyaksh.rag.sources.delete_notebook` | No page, rule or agent tool deletes a whole notebook. Keep it if that feature is planned. |
| `adhyaksh.services.voice.engine_running` | The Voice page asks `engine_voice()` instead. |

## Used only by tests

| Function | Note |
|---|---|
| `adhyaksh.services.chat.conversation_new` | The Chat page now starts a new chat without a row (chat-startup); tests still call it. |
| `adhyaksh.services.chat.conversation_title` | Only tests read titles this way; the sidebar uses `conversations_list`. |
| `adhyaksh.services.chat.reset_process_store` | Intended: it stands in for a server restart in tests. Keep. |
| `adhyaksh.tools.features.detect_objects` | The Object Detection page and chat use other entry points; only a test calls it. |

## Service aliases no page uses

These are one-line re-exports in the service layer that no page, other module or test uses any more.

| Alias | Why it became unused |
|---|---|
| `adhyaksh.services.activity.audit_list_recent` | The Activity page uses `rows()`. |
| `adhyaksh.services.chat.bridge_handle_audio` | The Chat page no longer listens (Voice page does). |
| `adhyaksh.services.chat.context_get` | The commented-out agent-steps block that used it was removed in 4e. |
| `adhyaksh.services.chat.context_latest_conversation` | The current chat now comes from `current_chat()`. |
| `adhyaksh.services.chat.context_new_conversation` | Same; new chats are created by `ensure_chat()`. |

## Requirements

| Item | Note |
|---|---|
| `pytest-cov` (requirements-core.txt) | Never imported and no command uses `--cov`. It could move out of the core list, or stay if coverage reports are wanted. |
| `pytest` (requirements-core.txt) | Used by the tests only; a runtime install does not need it. Consider a separate requirements-dev.txt. |
| `websockets` (not listed) | Imported by `hud/app.py` (and the screenshot tool). Streamlit itself requires it, so a clean install has it (checked in a fresh venv). Fine as is. |
| `torch` (comment only) | Needed only for the PyTorch MLP (M2), installed by hand as the comment says. Fine as is. |
| `pytesseract`, `clip` (not listed) | Optional fallbacks inside try/except (OCR without RapidOCR; YOLO-World). Fine as is. |
| `joblib`, `pydantic` (not listed) | Come in with scikit-learn and fastapi. Fine as is. |

## Left alone on purpose

- `adhyaksh/safety/verify.py` functions such as `_path_exists`: they look unused but are registered through the `@verifier` decorator.
- `tests/eval/results_baseline.csv` and `results_previous.csv`: `run_eval.py` reads them for the before and after table in docs/EVAL_REPORT.md.

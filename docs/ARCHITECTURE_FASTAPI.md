# Should ADHYAKSH move to FastAPI and a web front end?

Written in P7 (2026-11-17). Short answer: **not now, and not all at once.** Keep Streamlit as the user interface. When
one of the triggers below becomes real, add a small local FastAPI service *behind* the existing service layer.
Replace the Streamlit UI only if a second client or the UI limits listed below start costing more than the
rewrite.

## 1. Where the project stands

- Single user, single Windows laptop, everything on `127.0.0.1`. There are no remote users and no multi-tenant data.
- Since P6 the pages call only `adhyaksh.services.*` (one module per page, enforced by a test). The chat engine, tools,
  safety gateway, models and SQLite are already independent of Streamlit. Two exceptions are the voice bridge
  (a Streamlit custom component) and `st.cache_data` in `vision/descriptions.py`.
- Every action already returns a `Result` and goes through `policy.run_guarded`. L2 confirmations are token-based
  (`ConfirmationStore`), which maps directly onto an HTTP request and response pair.

So the expensive part of a FastAPI move, separating logic from the UI, is largely done. The question is whether
the benefit is worth a second process and a second code base.

## 2. What Streamlit costs us today

| Limitation | Effect on ADHYAKSH | How bad |
|---|---|---|
| Whole-script rerun on every interaction | The chat page re-renders history on each message; long pages feel slower | Moderate; fragments and caching keep it acceptable |
| Nothing runs without an open browser tab | Reminders fire only while a tab is open (20 s fragment poll); hands-free voice stops when the tab closes | **The main real limitation** |
| No server push | Progress for training, long agent runs or downloads is polled | Minor |
| Custom components need an iframe and a message bridge | The voice control (`voice_logic.js`) talks to Python through `declare_component` | Works; awkward to test end to end |
| Limited layout control | Polished with CSS tokens (P7); some widgets cannot be styled fully | Minor for a desktop tool |
| One Python process holds UI and models | A crash in a model load can take the UI with it | Low; failures are caught and logged since P6 |

What Streamlit gives us: a working UI in about 1,100 lines with no JavaScript build, free widgets for tables,
charts, camera and file upload, and one process to start (`run.bat`). The PyInstaller package also has only one thing to
start.

## 3. Options

| Option | What changes | Effort (estimate) | Gains | Costs |
|---|---|---|---|---|
| A. Stay on Streamlit | Nothing | 0 | Simplest; nothing new to break | Keeps the limits in section 2 |
| **B. Local FastAPI core, Streamlit stays the UI** | New `adhyaksh/api/` (FastAPI app over the existing services); a background scheduler for reminders and, later, voice; Streamlit pages call the API or stay in-process | 3 to 5 days | Reminders and wake word work without a tab; other clients become possible (tray icon, global hotkey, phone on the same Wi-Fi if ever wanted); clear contract for tests | Two processes to start and package; an authentication token to manage |
| C. FastAPI plus a new web front end (React, Svelte or htmx) | Rewrite all 9 pages | 3 to 6 weeks | Full control of layout, streaming replies, push updates, smaller per-interaction cost | Node toolchain and build, much more UI code to maintain, the Streamlit work is thrown away |

## 4. Recommendation

1. **Now: option A.** P0 to P7 met their targets (real eval 99.6%). The open risks are Windows checks of voice,
   packaging, PDF and keyed providers, not architecture. A rewrite now would move effort away from those checks.
2. **Next, when either trigger below happens: option B.**
   - Trigger 1: reminders or hands-free voice must work while no browser tab is open.
   - Trigger 2: a second client is wanted (system tray, global hotkey, another device).
3. **Option C only if** option B is in place and the Streamlit UI itself is the bottleneck: streaming replies,
   complex interactive layouts, or a public demo where look and feel matter more than speed of change.

## 5. How option B would look

```
browser (Streamlit UI)  -->  adhyaksh.services (in-process, as today)
tray / hotkey client    -->  http://127.0.0.1:8765  FastAPI  -->  adhyaksh.services --> engine, tools, safety, db
                                      |
                                      +-- scheduler thread: reminders, (later) wake-word listener
```

- One endpoint per service function. The P6 service modules are the list:
  - `POST /chat` with `{text, conversation_id, mode}`, returning the engine result.
  - `POST /confirm/{token}` and `DELETE /confirm/{token}` for L2 confirmations (the existing tokens).
  - `GET /health`, which returns `services.health.checks()`.
  - `GET /activity`, `GET/POST /memory`, `GET/POST/DELETE /reminders`, `GET /processes`.
- Request and response bodies are pydantic models built from the existing `Result` (`ok`, `data`, `error_code`, `message`),
  so the clear error messages from P6 reach every client unchanged.
- Security rules (required, not optional):
  - Bind to `127.0.0.1` only.
  - Require a random token generated on first start, stored in the data folder and sent as a header.
  - Turn CORS off.
  - Keep the safety gateway in the server, so no client can skip L2 confirmation or the allowed folders.
  - Never return API keys; the Health endpoint keeps reporting keys only as present or absent.
  - Cloud use stays behind `cloud_consent`, checked on the server.
- Reminders move from the Streamlit fragment to the scheduler thread, which shows a Windows notification (through a
  tray client or a small notification package, chosen and measured at that time). The sidebar toast can stay as a second channel.
- Tests: FastAPI's `TestClient` lets the API be tested without a network, the same way the evals run today.
- Packaging: the launcher starts uvicorn in a thread, then Streamlit, so the user still starts one program.

New dependencies for option B: `fastapi` and `uvicorn`, plus `pydantic`, which may already be present through
other packages. Their disk size is small, a few MB, but it was **not measured** because nothing was installed in P7.
Measure it with `pip install fastapi uvicorn` in a scratch environment and record it in docs/UPGRADE_LOG.md before
adopting option B.

## 6. What to keep doing whichever option is chosen

- Pages call only services (the P6 test keeps this true). Every new feature gets a service function first.
- Keep Streamlit-specific code (`st.cache_data`, components) out of `adhyaksh/` packages other than `ui/` and
  `voice/bridge.py`. Moving `vision/descriptions.py` to a plain cache is a small first step.
- Keep `Result` as the only way results cross a boundary. It is what makes options B and C cheap.

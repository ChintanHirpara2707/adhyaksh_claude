# JARVIS upgrade plan (Phase 0 audit)

Written 2026-11-19 after a full read of the code. Each phase ends with the full test suite, both evals and the
user's go-ahead before the next one starts. Progress is recorded in docs/UPGRADE_LOG.md as before.

## Baseline (measured at the start of Phase 0)

Measured 2026-11-19 on `main` at e8395cb, before any Phase 1 change:

| Check | Result |
|---|---|
| `pytest tests -q --ignore=tests/test_tools.py` | 646 passed, 2 skipped (9 min 26 s) |
| `nlu.dataset validate` | valid |
| Regression suite `tests/eval/run_eval.py` | 398/399 (C347 known) |
| Real eval `tests/eval/run_real_eval.py` | 237/238, 99.6% (R054 known) |
| Active model test macro-F1 (`docs/RESULTS.md`) | 0.956 |

Gate for every phase: no lower number in any row.

## 1. Audit findings by subsystem

### 1.1 Request flow today
`chat/engine.handle_message` has two completely separate execution paths:

- **Model available** (local Ollama, or cloud with consent): every message goes to `agent/native.py`, even
  "open notepad". Every simple command needs one or more round trips to the language model, so it is slower, does not
  work offline, and sends text to the cloud that the local rules could have handled.
- **No model**: `router.understand` (about 180 regexes and matcher functions in 1,409 lines), then the TF-IDF
  classifier, then `engine._dispatch`, which is a 53-branch `if intent == ...` chain that calls the tools directly and
  builds its own replies.

The two paths share the tools but nothing else: argument handling, confirmation, verification and reply wording are
all written twice. A fix in one path does not reach the other (the app-close bug had to be fixed in both).

### 1.2 Language model layer (`llm/`)
| Gap | Where | Effect |
|---|---|---|
| Native tool calling only; no JSON fallback | `llm/base.py` `chat()` | A model without tool support returns HTTP 400 and the agent gives up ("the model may not support tools"). Groq's `tool_use_failed` 400, which includes the model's malformed output, is thrown away instead of repaired. |
| No capability profile | `get_provider()` | The app cannot know whether a model supports tools, JSON mode or images, so it cannot choose a strategy. |
| Malformed tool arguments become `{}` silently | `groq.parse_openai_message`, `ollama._chat` | The tool then fails with `KeyError`, and the model sees only "raised KeyError", so it cannot correct itself. |
| No argument validation against the schema | `agent/registry._guarded` | Missing or wrongly typed arguments reach the tool. |
| Only three providers, no OpenAI-compatible endpoint | `llm/base.PROVIDERS` | LM Studio, llama.cpp server, vLLM and OpenRouter cannot be used. |
| Six direct `requests.post` calls skip `net.py` | groq, gemini, ollama | No 429 or 5xx back-off on the main chat calls (only `embed` goes through `net`). |
| Two agent loops | `agent/native.py` and `agent/runner.py` | `runner.py` (text protocol `TOOL: {json}`) is only reached after the native agent has already failed against the same model, so in practice it is dead weight that still has to be maintained. |

### 1.3 NLU (`nlu/`, `chat/router.py`)
| Gap | Effect |
|---|---|
| Action polarity is baked into flat intent labels (`app_open`/`app_close`, `file_create`/`file_delete`, `reminder_set`/`reminder_cancel`) | The classifier must learn every opposite pair separately from sparse words, and nothing in the design stops an opposite-action mistake. The engine adds a hand-written `_INTENT_SIGNAL` regex table afterwards to catch them. |
| No negation handling | "don't close chrome" or "notepad band mat karo" are understood as a close. |
| The router grew by phase (`match_p1`, `match_cowork`, `match_extended`, `_match_more`) | Order-dependent regexes; a new phrase means another regex; the rules overlap with the classifier instead of complementing it. |
| Slot extraction lives inside the matchers | The same entity (an app, a file) is extracted differently by different matchers; the agent path does not use these extractors at all. |
| No numbers with units (volume 40 percent, brightness up by 10) and no generic set/increase/decrease frame | New system controls would need yet more special regexes. |
| Training data is template-generated with no opposite-polarity minimal pairs and no speech-recognition noise | High test macro-F1 (0.956) but brittle on real phrasing; `data/intents.csv` and `test_codemixed.csv` are still marked UNREVIEWED. |

### 1.4 Agent (`agent/`)
- Loop is bounded (6 steps) and safe (L2 pause, claim guard), but has **no verification**: success is whatever the tool
  returned; nothing checks that the file exists or the app really opened.
- No error recovery policy: the model may retry anything, including actions that should not be retried, or give up at once.
- No way to ask a clarifying question except free text; no loop detection (the same failing call can repeat to the limit).
- Pending confirmations (`_PENDING`, `ConfirmationStore`) live in process memory: a restart loses them (this matters once there is a background service).

### 1.5 Tools and OS control (`tools/`)
Present: files, Office, apps (allow-list), special folders, web open (browser only), screenshot, OCR, system status,
processes, reminders, clipboard, temp clean, vision.
Missing: speaker and microphone volume, brightness, Wi-Fi and Bluetooth state, lock/sleep/shutdown, window management
(focus, minimise, close a window by title), active-window capture, battery events, **reading a web page** (only
`web_open`, which opens a browser tab, and a Wikipedia summary), and live search answers.

### 1.6 Memory (`memory/store.py`)
Facts are free-text rows matched by shared words. There is no subject or attribute, so "my favourite colour is red" after
"... is blue" stores a second, contradicting fact, and recall picks whichever shares more words. Facts are saved only
when the user uses a known phrase such as "remember that".

### 1.7 Voice, HUD and background work
- Voice runs inside the Streamlit browser tab (Web Speech API plus optional local Whisper). With the tab closed there is
  no wake word, no voice and no reminders. Voice is still untested on the target PC.
- There is no background process and no desktop presence. `docs/ARCHITECTURE_FASTAPI.md` (P7) already recommended a
  local FastAPI core for exactly these reasons.

### 1.8 What is solid and is kept
Safety gateway (L0 to L3, confirmation tokens, audit log), folder sandbox, app allow-list, JSON-lines logging with
redaction, `net.py` timeouts, settings validation, the service layer boundary for pages, and the two evals
(399 regression cases, 238 real commands).

## 2. Target architecture

```
 text / voice / HUD / Streamlit
            |
     1. Normalise        script, fillers, typos, speech noise
     2. Frame parser     action + polarity + negation | target type + entities (app, file, url, number, time, fact)
     3. Router           complete, confident, single-step frame  -> local fast path
                         otherwise                                -> agent
     4. ToolCall(name, args)   one representation for both paths
     5. Executor         schema validation -> safety gateway (L0-L3) -> tool -> post-condition check -> audit
     6. Reply builder    one place, persona rules, five languages
```

The rules, the classifier and the language model all produce the **same thing** (a `ToolCall` against the one tool
registry), so validation, safety, verification and replies are written once.

## 3. Phases

Each phase is split into sub-steps that each end in a commit on a new branch `jarvis-upgrade` (never pushed).
Every new dependency gets its disk size recorded. Free and light tools only.

### Phase 1: Universal brain and NLU
**1a. Provider-agnostic tool calling** (`llm/`, `agent/`)
- `Capabilities` per provider and model (native tools, JSON mode, images, context size), from a known table, a
  setting override, and learning: a tools rejection marks the model as no-native and is remembered.
- Two strategies behind one `ToolCaller` interface:
  - **Native**: provider function calling, as now.
  - **JSON protocol**: tool schemas in the prompt; the model must reply with `{"tool_calls": [...]}` or
    `{"answer": "..."}`. A tolerant extractor handles code fences and extra text.
- Strict validation of every call against its JSON schema (types, required, enums; a small built-in validator, no new
  dependency), with argument coercion ("40" to 40).
- **Self-healing**: a malformed call or a validation error is sent back to the model as a precise error ("argument
  `app` is required; allowed values: ...") for up to two repairs. Groq's `failed_generation` is salvaged. A tools 400
  switches to the JSON strategy and retries once.
- New `openai_compat` provider (base URL and model in settings, key in `.env`), covering LM Studio, llama.cpp, vLLM and OpenRouter.
- All provider calls go through `net.py` (429 and 5xx back-off, Retry-After).
- `runner.py` is retired; its step labels move to the one loop.

**1b. Frame-based NLU** (`nlu/frames.py`, `nlu/lexicon.py`, `nlu/entities.py`)
- A multilingual action lexicon: open, close, create, delete, read, update, search, enable, disable, increase,
  decrease, set, show, save, forget, remind and cancel, each with English, Hindi, Gujarati, Hinglish and Gujlish verb
  forms, plus negation words (don't, mat, nahi, नहीं, મત, નહીં).
- Entity extractors, each returning a clean normalised value: app (allow-list plus fuzzy match), file and folder,
  URL and site, number with unit (percent, levels), time (reuses `tools/when.py`), process name or pid, memory fact.
- A table `(action, target type) -> tool` decides the intent, so opposite actions cannot collide by design; a negated
  command is never executed.
- Factorised classifier: alongside the flat intent model, a model for the **action** and one for the **target type**,
  combined through the same table and cross-checked with the flat model. Disagreement means ask or use the agent, not guess.
- The phase-named matchers are migrated into frames step by step, each step gated by the evals. Kept as special rules:
  maths, multi-line memory and multi-step splitting.
- Local fast path when a model is configured (setting `routing`: `local_first` by default, or `llm_first`).

**1c. Data, retraining and evaluation**
- The generator adds opposite-polarity minimal pairs, negations, speech-recognition noise ("note pad", "crome") and
  code-mixed grammar for every action and target pair.
- New eval suites:
  - **polarity**: minimal pairs, where both members of each pair must pass;
  - **slots**: the extracted argument must equal the normalised gold value;
  - **negation**: nothing may run.
- Run `nlu.dataset validate`, `nlu.train --all`, and regenerate `docs/RESULTS.md`.
- Gate: no lower pass rate on either existing eval.

### Phase 2: Autonomy and OS mastery
**2a. Agent loop: Plan, Execute, Observe, Verify, Correct**
- A post-condition check per tool (file exists, process running or gone, volume reads back the value).
- Error results carry `retryable` and a `hint` (for example "not found; similar: notes.txt").
- Bounded budgets: steps, time, and at most two retries per tool. L2 and destructive actions are never retried automatically.
- Loop detection: the same failing call twice stops the loop.
- An `ask_user(question, options)` tool, used only for real ambiguity; the answer resumes the plan.
- The offline multi-step path uses the same executor and verifier.

**2b. New tools** (all through the safety gateway; levels shown)
| Tool | Level | How (free, light) |
|---|---|---|
| Speaker and mic volume: get, set, step, mute | L1 | `pycaw` + `comtypes` (about 2 MB) |
| Brightness: get, set, step | L1 | `screen-brightness-control` (small) or WMI; laptops only |
| Wi-Fi and Bluetooth: status | L0 | `netsh` read-only, fixed arguments, no shell |
| Wi-Fi and Bluetooth: on and off | L2 | WinRT radios API if it works without admin; otherwise reported as unsupported, not faked |
| Battery and power plan | L0 | `psutil` |
| Lock | L1 | `user32.LockWorkStation` |
| Sleep, restart, shut down | L2 | fixed commands with a cancel window |
| Windows: list, focus, minimise, maximise, close by title | L1 | `ctypes` user32, no dependency |
| Look at my screen: active-window capture, OCR, objects and explanation | L0 | existing OCR and YOLO; images go to a cloud model only with a separate `cloud_vision_consent` |
| Read a web page: text, title, description and links | L0 | `net.get`, http(s) only, private and localhost addresses blocked (SSRF guard), 2 MB cap, HTML to text with the standard library |
| Search and answer | L0 | a keyless search page, then the top 2 or 3 pages fetched and summarised (by the model with consent, otherwise extractively) |

**2c. Structured memory**
- Facts get `subject`, `attribute`, `value`, `source`, `confidence` and `updated_at`.
- Saving the same subject and attribute again updates the fact instead of adding a duplicate. "Forget my X" deletes it.
- Recall matches by attribute first, then by embedding similarity (the existing embedder).
- Automatic extraction from normal conversation (rules, plus the model when allowed) is behind an `auto_memory` setting that is off by default and visible on the Memory page.
- A migration converts the existing facts.

**2d. Persona**
- New system instructions: short and calm by default, a one-line confirmation for actions, depth only when asked or
  when the task needs it, never an invented result, and the user's language.
- The reply builder templates are rewritten to the same style.

### Phase 3: Background engine and desktop HUD
**3a. `adhyaksh/server.py`** (FastAPI + uvicorn, about 10 MB)
- Bound to 127.0.0.1 only.
- A random per-install token and an `Origin` check, so web pages in the browser cannot send commands to localhost.
- `POST /v1/message`; `WS /v1/events` for state (idle, listening, thinking, speaking, executing), steps and confirmations.
- Pending confirmations are stored in SQLite, so they survive a restart.
- The Streamlit services call the server when it is running and run in-process otherwise (one code path).
- Watchdog: low battery, sustained CPU or temperature spikes, low disk, and due reminders (so reminders no longer need the browser tab).
- Optional autostart via a Startup-folder shortcut (no admin, no Windows service).

**3b. Native voice pipeline**
- Microphone: `sounddevice`. Speech detection: the energy-based VAD already used.
- Wake word: `openWakeWord` (ONNX, small).
- STT: `faster-whisper`, already used.
- TTS: Windows SAPI voices through `pyttsx3`, with Piper as an optional higher-quality Hindi and Gujarati voice (about 60 MB per voice).
- Barge-in: speaking stops when the user talks.

**3c. HUD** (`hud/`)
- tkinter (standard library, 0 MB): frameless, always on top, transparent background, animated ring per state.
- Global hotkey with `RegisterHotKey` (ctypes, no dependency); WebSocket sync with the server.
- Rejected: PySide6 (150 to 250 MB) and Electron or Tauri (Node toolchain), both against the light-tools rule.

## 4. Risks and what cannot be verified here
- Volume, brightness, radios, power, window control, microphone, wake word, TTS and the HUD need the real laptop.
  Tests here mock the OS calls; each phase adds the items to the hand-test list in UPGRADE_LOG.
- Wi-Fi and Bluetooth switching may need admin rights on some PCs; if so the tool says so instead of pretending.
- Calls to a keyed cloud model are still untested here (no key is used in tests).
- Each phase is several sessions of work; sub-steps keep every commit working and reversible.

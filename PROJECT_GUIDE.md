# ADHYAKSH Project Guide

Contents

- Part A. One-page summary (what it is, features, tech, flow, ten examiner questions)
- Part B. The pages: what the user sees
- Part C. The code, file by file
- Part D. One message from typing to reply
- Part E. The models: what, why, how trained, how good
- Part F. The database
- Part G. Safety: levels L0 to L3, confirmation, audit
- Part H. Voice, vision, attachments and document Q and A (RAG)
- Part I. Libraries, and how to run, test and train
- Part J. Known limits and honest caveats

---

## Part A. One-page summary

### A1. What it is

ADHYAKSH ("chairperson" in Hindi) is a private assistant that runs on your own Windows laptop and that you talk to in a chat window. You can type or speak. It understands English, Hindi, Gujarati, and the two mixed styles people really use: Hinglish (Hindi written in English letters, mixed with English) and Gujlish (the same for Gujarati).

"Local-first" means the program works on your computer, with your files, and sends nothing to the internet unless you switch that on. "Private" means that by default no question, file or memory leaves the machine.

An analogy: think of a capable office assistant sitting at your desk. They can open your apps, find your files, remember facts you tell them, read the documents you hand them, tell you how the computer is doing, and look at a photo. A security guard stands behind them and checks every action before it happens. That guard is the "safety gateway" (Part G).

### A2. Main features

| Feature | What you can say or do |
|---|---|
| Chat | Ask anything. Small talk, maths, time and date, general knowledge |
| Files and folders | Create, read, add to, delete and search files; make folders; make Excel and Word files |
| Apps | Open and close applications from an approved list; open websites; open Downloads, Desktop, Recycle Bin |
| System | "How is my CPU?", take a screenshot, show the PC Performance page, clean old temp files |
| Memory | "Remember that my locker code is 4471", "what is my locker code", "what do you remember" |
| Documents | Attach a PDF, Word or text file to a chat message and ask questions about it, with sources |
| Vision | Attach a photo and get a list of objects; a separate page uses the camera |
| Voice | Speak commands, hands-free listening, optional wake word "Adhyaksh", spoken replies |
| General AI answers | Optional: a local model (Ollama) or a cloud model (Groq or Gemini) when you allow it; Wikipedia as a free fallback |
| Model Lab | Look at the intent models, their scores, add training examples, retrain |
| Activity log | A permanent record of everything the assistant did or refused |

### A3. Technology used

| Layer | Technology | In one line |
|---|---|---|
| Language | Python 3.11 or 3.12 | The programming language of the whole project |
| Screen | Streamlit | Turns Python scripts into web pages shown in your browser |
| Storage | SQLite | A database kept in a single file on your disk |
| Understanding | scikit-learn: TF-IDF, Logistic Regression, SVM; PyTorch MLP | Small machine-learning models that guess what you want |
| Vision | Ultralytics YOLOv8, YOLO-World | Models that find objects in pictures |
| Voice | The browser's Web Speech API | The browser itself listens and speaks; no extra program |
| Language models | Ollama (local), Groq and Gemini (cloud, only with consent) | Optional, for open-ended answers |
| Tools | psutil, Pillow, send2trash, openpyxl, python-docx, PyMuPDF | Computer stats, screenshots, safe delete, Excel, Word, PDF |

### A4. The flow of one message in ten lines

1. You type or speak a message in Chat. Speech is turned into text by the browser.
2. The chat page hands the text (and any attached files) to the engine.
3. The engine checks whether it is answering an earlier question (for example "Which file name?" or "Confirm delete?").
4. The rule layer (the router) tries fixed patterns first: greetings, maths, "remember ...", "open notepad", "stop listening", and many more. A rule hit is instant and certain.
5. If no rule fits, the intent model reads the text and returns a guess, such as "file_delete", with a confidence number.
6. If the model is unsure, or the text is clearly a general question, the engine routes it to the general-answer path instead of guessing a tool.
7. The engine fills in the details (the slots), for example which file or which app.
8. Any action is sent through the safety gateway, which checks the level (L0 to L3), the allowed folders and the app list, asks for confirmation when needed, and writes an audit row.
9. The tool does the work (or is refused) and the engine writes a reply from a template in your language.
10. The reply is saved to the database, shown in the chat, and optionally spoken.

### A5. Ten questions an examiner is likely to ask

1. **What problem does it solve?** It gives one private place to control a laptop and answer questions in the languages people in Gujarat and India actually mix, without needing a cloud service.
2. **Why not just send everything to a big language model?** Privacy, cost, and speed. Most commands ("open notepad") do not need a large model. A small trained classifier plus rules answers in milliseconds, offline. A large model is optional for open-ended questions.
3. **How does it understand a command?** Two layers. First rules (exact patterns written by hand), then a trained intent classifier (a model that picks one of 28 labels such as `app_open`). Details such as the file name come from separate extraction code.
4. **Which model is active and how good is it?** A calibrated linear SVM on TF-IDF features. On the held-out test split: accuracy 0.930, macro-F1 0.886 (macro-F1 is explained in Part E). On a separate code-mixed file: macro-F1 0.900. Caveat: the training data is synthetic, so real-user accuracy is expected to be lower.
5. **How was it trained, and is there data leakage?** Training rows are generated from hand-written templates (3,143 rows, 28 intents, all marked unreviewed). The test split shares templates with training, so its score is optimistic. The code-mixed file uses different wording and has zero text overlap with training (checked). A 399-sentence evaluation set is also kept out of training and checked on every run.
6. **How do you keep it from doing something dangerous?** Every action goes through one gateway. Actions have levels: L0 read only, L1 reversible, L2 destructive (needs your confirmation), L3 never allowed. File work is limited to folders you allow, apps to a list you approve, and every attempt is written to an append-only audit log.
7. **What leaves the computer?** Nothing by default. Only if you turn on "cloud consent" and add a key do questions go to Groq or Gemini, or a question to Wikipedia. Keys live in a git-ignored `.env` file, never in the database or the logs.
8. **How do documents work (RAG)?** RAG means retrieval-augmented generation. The file is cut into short overlapping pieces; when you ask a question the program finds the pieces most similar to it (TF-IDF similarity) and shows them with file name and page. With cloud consent a language model can phrase the answer from those pieces.
9. **How is Hindi and Gujarati handled?** The tokenizer keeps Devanagari and Gujarati letters and vowel signs together, the features include character n-grams so spelling variants help, and rules and templates exist in all five language styles. Reply templates exist in English, Hindi and Gujarati.
10. **What are the weaknesses?** Synthetic and unreviewed training data; no native-speaker review of Hindi and Gujarati; voice, PDF reading, Windows app launching and keyed cloud calls were not tested on the target laptop; the 399-case evaluation score (398 of 399) is a regression check, not a blind test, because rules were written while reading its failures.

---

## Part B. The pages: what the user sees

The app opens in your browser. A left sidebar has a Light/Dark switch and links to eight pages. (An earlier "Documents" page was removed: documents are now attached inside Chat.) The pages are Python files in the `pages/` folder, and `app.py` lists them. Streamlit is the tool that draws them; each page is a short script that runs from top to bottom every time you click something.

### B1. Sidebar and first run

- **Theme switch.** Light or Dark. The choice is saved in the database, not in the web address.
- **First run.** If the app does not know your name yet, Chat shows a small form asking for it. You can change it later by saying "my name is ...".

### B2. Chat (`pages/chat.py`)

This is the main page. You see:

| What you see | What it does |
|---|---|
| Header "Chat" | Page title and a one-line hint |
| "New conversation" button | Starts a fresh conversation (old ones stay in the database) |
| Message list | Your messages and the assistant's replies. A "Wrong intent?" button under each reply lets you tell the system what you really meant; the correction is saved for the next retraining |
| Confirmation card | Appears when an action needs your approval (for example deleting a file): Confirm or Cancel |
| Voice control strip | Language choice, "Speak once", "Start hands-free", a wake-word checkbox, "Stop speaking" and a status line |
| Mode switch | **Chat** mode answers and informs only. **Cowork** mode can also open apps and work with your files. If you ask for an action in Chat mode, it offers a "Switch to Cowork" button |
| "Attached documents" box | Lists indexed documents with a Remove button each |
| Message box with a paperclip | Type a command, or attach PDF, DOCX, TXT, MD, CSV files, or JPG, PNG, WEBP photos |

Useful things to try: "create notes.txt", "remember that my car is Audi", "what is my car", "show system status", "open notepad", "take a screenshot", "which apps use the most RAM", "stop listening", or ask any general question. Answers from the general-question path and the agent are shown word by word.

### B3. Memory (`pages/memory.py`)

A list of facts the assistant remembers. You can add a fact, search, edit a fact, or delete it. Facts saved by chat ("remember ...") appear here.

### B4. Tools (`pages/tools.py`)

Three plain sections: a CPU, memory and disk readout with a Refresh button; a table of files in your workspace folder; and a list of allowed applications with Open and Close buttons. Closing asks for confirmation. Everything here goes through the same safety gateway as chat.

### B5. Model Lab (`pages/model_lab.py`)

For people who want to see how the understanding works. Three tabs:

- **Comparison.** A table of trained models with accuracy, macro-F1, code-mixed F1, file size and speed; a button to make one model the active one; per-language scores; a confusion matrix (a grid showing which intents get mixed up with which).
- **Dataset.** How many training rows each intent has; a form to add or correct an example sentence; the latest rows.
- **Training.** One button, "Train all models", which trains in the background while you keep chatting, with a live log.

### B6. Activity (`pages/activity.py`)

A table of the most recent 50 actions: time, action, target, level, whether it was confirmed, and the result. The log cannot be edited or erased by the app (Part G).

### B7. Settings (`pages/settings.py`)

| Section | What it controls |
|---|---|
| Folders | Which folders the assistant may touch, and the default work folder |
| Assistant | Confidence threshold slider, which intent model is active, "speak replies aloud" |
| Language model and cloud use | Provider (none, Groq, Gemini, Ollama), API key box (masked), model names, and the consent checkbox. A warning shows when cloud use is on |
| Power mode (dangerous) | Allows a Python-running tool inside a restricted sandbox; off by default; every run needs confirmation |
| Applications allow-list | The apps the assistant may open or close, as editable JSON; minimum document match score |
| Your data | Download a copy of the database, or delete all data (needs a tick-box) |

### B8. Object Detection (`pages/vision.py`)

Take a camera snapshot or upload an image. Choose a model size (Fast, Balanced, Accurate), an image size, a confidence threshold, and a mode:

- **Standard**: the 80 everyday object types the model knows.
- **Small objects**: scans the picture in tiles so small things are found; slower.
- **Any object I name**: you type words ("mug, stapler") and an open-vocabulary model looks for them; needs a large one-time download.

An option adds general category guesses (1,000 ImageNet classes). The page draws red boxes, groups results ("3 cups, best confidence 91%"), gives a two-sentence description of each object, and has a "Details" box with technical facts.

### B9. PC Performance (`pages/performance.py`)

Four live gauges (CPU, RAM, disk, size of old temp files) that refresh every 3 seconds, and a "Boost PC" button that scans for temp files older than a day, then offers "Clean now" or "Cancel".

---

## Part C. The code, file by file

Words used below: a **module** is one Python file; a **function** is a named block of code that does one job; a **class** is a bundle of data and functions; a **Result** is a small standard envelope (success or failure plus data) that tools return so callers never have to catch surprises.

### C1. Top level

| File | Purpose |
|---|---|
| `app.py` | Entry point. Starts logging and the database once, builds the page list and the sidebar |
| `run.bat`, `run.sh` | One-click launchers: create a virtual environment (a private folder of libraries), install requirements, start Streamlit |
| `requirements-core.txt`, `requirements-optional.txt` | Library lists. Optional: sentence-transformers, easyocr, ultralytics |
| `pytest.ini` | Tells the test runner where tests are |
| `.streamlit/config.toml` | Look and server settings (headless, no usage tracking) |
| `.env` and `.env.example` | Where API keys go. `.env` is ignored by git; the example only shows the variable names |
| `CLAUDE.md`, `AGENTS.md`, `README.md`, `CHANGELOG.md` | Notes for people and coding assistants |
| `PROJECT_GUIDE.md` | This file |

### C2. `adhyaksh/` core modules

| File | Purpose and key functions | Why it exists |
|---|---|---|
| `__init__.py` | Holds the version number | Standard package marker |
| `config.py` | Folder paths, the `DEFAULTS` dictionary of settings, `get`, `set_value`, `get_bool`, `get_float`, `get_allowed_roots`, `configure_folders`, default app list | One place for every setting; settings live in the database so they survive restarts |
| `db.py` | The only code that talks to SQLite: `init`, `execute`, `query_all`, `query_one`, `get_setting`, `set_setting`, `backup`, `restore`, `export_bytes`, `wipe` | Keeping all database access in one file makes it easy to check and test |
| `result.py` | `Result` (with `success` and `failure`) and error codes such as `E_NEEDS_CONFIRM` | Every tool answers in the same shape |
| `responses.py` | `t(key, lang)`: reply templates in English, Hindi, Gujarati | Replies are formal and consistent; no reply text is scattered in code |
| `logging_setup.py` | `setup`, `redact`: a log file that automatically blanks anything that looks like a secret | Keys must never appear in logs |

### C3. `adhyaksh/chat/` the conversation brain

| File | Purpose and key functions | Why it exists |
|---|---|---|
| `engine.py` | `handle_message` (the front door), `_process` (the decision order), `_dispatch` (do the intent), `confirm`, plus handlers for files, apps, memory, vision, performance, voice, general questions | The one place where a message becomes an action and a reply |
| `router.py` | The rule layer. `understand` (try every rule family), `match_rules`, `match_extended`, `match_conversational`, `match_features`, `match_memory`, `parse_web_command`, `safe_eval` (maths without `eval`), slot extractors `find_file`, `find_app`, `find_folder_name`, `clean_command`, `fix_verb_typo`, `voice_action` | Rules are fast, free, predictable and cover the commands that must never be guessed |
| `numwords.py` | `normalize`: turns "paanch plus saat" or "twenty five minus ten" into digits | Spoken arithmetic in English, Hindi and Gujarati |
| `identity.py` | `extract_name`, `save_name`, `get_name` | Learns and recalls your name safely (ignores "my name is not ...", questions, hypotheticals) |
| `context.py` | `Context` (short-term memory per conversation: last file, last app, pending question, pending confirmation, attached images), `save_message`, `history`, `new_conversation` | Lets "delete it" or a follow-up answer make sense |

### C4. `adhyaksh/nlu/` natural language understanding

| File | Purpose and key functions | Why it exists |
|---|---|---|
| `dataset.py` | The 28 intent names, the template lists and word pools, `generate`, `augment`, `augment_knowledge`, `augment_features`, `validate`, `split`, `add_example`; command line: `python -m adhyaksh.nlu.dataset generate/augment/validate/report` | Builds and checks the training data |
| `features.py` | `build_vectorizer`: TF-IDF over words and over characters, with a tokenizer safe for Hindi and Gujarati | Turns sentences into numbers |
| `models.py` | `SklearnIntentModel` (logistic regression, calibrated SVM), `TorchMLPModel`, `make`, `load` | The three classifiers |
| `train.py` | `train_all`, `start_background`, `status`; command line `python -m adhyaksh.nlu.train --all` | Trains, scores, saves, registers, picks the best on validation |
| `evaluate.py` | `compute_metrics`, `tune_tau`, `measure_latency`, `write_results_md` | Scores and the generated `docs/RESULTS.md` |
| `registry.py` | `register`, `set_active`, `predict` (returns intent, confidence, gap to second place) | Remembers which trained model is active and answers one prediction fast (model cached in memory) |

### C5. `adhyaksh/llm/` optional language models

| File | Purpose | Why |
|---|---|---|
| `base.py` | `Provider` base class, `ask`, `available`, `is_local`, `get_provider`, key reading from `.env`, `mask`, the system prompt | One door for every provider; consent is checked here |
| `groq.py`, `gemini.py` | Cloud calls over HTTPS (also `embed` for Gemini) | The two supported cloud providers |
| `ollama.py` | Calls a model on your own computer at 127.0.0.1 | Free and fully private; no key or consent needed |
| `wiki.py` | `lookup`: Wikipedia search and summary | A keyless fallback for factual questions (only with consent) |
| `cache.py` | A small in-memory answer cache with expiry | Avoids paying twice for the same prompt |

### C6. `adhyaksh/rag/` document questions

| File | Purpose |
|---|---|
| `loader.py` | `ingest_bytes`/`ingest`: read PDF, DOCX, TXT, MD, CSV, cut into chunks, store; `list_documents`, `delete_document`. Limit 25 MB per file |
| `chunker.py` | `chunk_text`: pieces of about 500 characters with 100 characters overlap |
| `retriever.py` | `retrieve`: finds the best pieces by TF-IDF similarity (or Gemini embeddings when allowed) |
| `answerer.py` | `answer`: returns the best pieces with their sources, or a model-written answer when cloud use is allowed |

### C7. `adhyaksh/memory/`

`store.py`: `save_fact` (strips command words, detects duplicates), `recall` (keyword overlap search), `list_facts`, `update_fact`, `delete_fact`. A simple, transparent memory: no model needed.

### C8. `adhyaksh/safety/`

| File | Purpose |
|---|---|
| `policy.py` | Levels L0 to L3, `authorize`, `run_guarded` (the single gateway), `cancel_guarded`, `deny`, folder rules |
| `confirm.py` | Short-lived confirmation tokens (5 minutes) for L2 actions |
| `audit.py` | `record` and `list_recent` for the append-only log |

### C9. `adhyaksh/tools/` the things the assistant can do

| File | Purpose |
|---|---|
| `files.py` | `create`, `read`, `update`, `delete` (to the Recycle Bin), `search`, `create_folder`, `list_dir`; all folder-checked |
| `office.py` | `create_workbook` (Excel), `create_document` (Word), `names_example`; never overwrites |
| `apps.py` | `open_app`, `close_app`, `allowlist`; no shell, only approved commands |
| `system.py` | `status` (CPU, RAM, disk), `screenshot`, `web_open`, `open_special_folder` |
| `boost.py` | `stats`, `scan_temp`, `clean_temp` (temp files older than 24 hours; skips links and files in use) |
| `features.py` | The guarded tools behind the vision, performance and voice intents: `perf_report`, `temp_scan`, `temp_clean`, `detect_objects`, `open_page`, `voice_command` |

### C10. `adhyaksh/agent/` the optional multi-step agent

`runner.py` asks a cloud model to choose tools step by step (maximum 6 steps), wraps every tool result as clearly marked data so a hostile web page or file cannot give it orders, and pauses when an L2 confirmation is needed. `registry.py` lists the tools the agent may use with their levels, and holds the restricted `run_python` sandbox (blocked imports, workspace-only file access, 30-second limit, confirmation every time, only when Power mode is on). The agent runs only when a cloud provider, a key and consent all exist.

### C11. `adhyaksh/ui/`, `voice/`, `vision/`

| File | Purpose |
|---|---|
| `ui/theme.py` | The Light and Dark colours as named tokens and the CSS built from them |
| `ui/components.py` | Reusable pieces: `page_header`, `empty_state`, `error_state`, `confirmation_card`, `first_run_form`, `chat_width` |
| `ui/icons.py` | The icon of each page in the sidebar |
| `voice/bridge.py` | `voice_input` (draws the voice strip and returns what was heard), `speakable` (cleans text before it is spoken) |
| `voice/component/index.html` | The small web page with the JavaScript that talks to the browser's speech features |
| `vision/detector.py` | `detect`, `detect_tiled`, `detect_open_vocab`, `classify`, `nms` (merge overlapping boxes), `parse_classes`, caching |
| `vision/descriptions.py` | `describe` (two sentences for each of the 80 object types) and `wikipedia` (optional summary) |

### C12. `tests/`, `data/`, `models/`, `docs/`

| Folder or file | What is there |
|---|---|
| `tests/test_*.py` | Automatic checks, grouped by area: chat, routing, modes, commands, memory commands, features (vision, performance, voice), RAG, vision, voice bridge, policy, guard, database, dataset, models, theme, static scans (no emojis, no forbidden calls, no secrets), web commands, boost, tools |
| `tests/helpers.py` | `fresh_env`: gives each test a throwaway data folder and database |
| `tests/eval/` | `cases.csv` (399 sentences across 13 sections and 5 languages), `run_eval.py` (runs them with every tool faked), result files from three runs |
| `data/intents.csv` | The training sentences (3,143 rows) |
| `data/test_codemixed.csv` | 182 held-out Hinglish and Gujlish sentences, never used for training |
| `data/test_author.csv` | A small set of author-written cases kept out of training |
| `data/adhyaksh.db` | The database file (git-ignored; created on first run) |
| `models/` | Trained intent models and YOLO weight files (git-ignored) |
| `docs/` | Project notes. `RESULTS.md` and `EVAL_REPORT.md` are generated; some older docs (for example `FILES.md`, `TESTS.md`, `DATA_CARD.md`) describe earlier versions and are partly out of date |

---

## Part D. One message from typing to reply

Follow the sentence "delete old.txt" from the keyboard to the screen. Files named here are explained in Part C.

### D1. The journey, step by step

| Step | Where | What happens |
|---|---|---|
| 1 | `pages/chat.py` | You press Enter. The page calls `engine.handle_message(text, conversation_id, mode, attachments)`. For speech, the browser converts your voice to text first and the page passes that text in the same way |
| 2 | `engine.handle_message` | Trims the text (up to 8,000 characters), detects the script (Devanagari means Hindi, Gujarati script means Gujarati, otherwise English), saves your message to the `messages` table. Photos in attachments go straight to the vision handler; documents are indexed first (Part H) |
| 3 | `engine._process` | Checks whether you are answering an earlier question: "yes" or "no" to a confirmation card, a missing detail ("Which file name?"), or "my name is X, confirm?" If so, it continues that earlier action |
| 4 | `router.understand` | The rule layer. Tries, in this order: memory commands (save, list), conversational rules (name questions, thanks, goodbye, help), feature rules (voice, vision, performance, unsupported actions such as "shut down my laptop"), the classic rules (greetings, maths, web commands, "create a file named ...", screenshots, special folders, apps), and finally the extended rules (synonyms, typos, Hindi and Gujarati phrasings, time and date, notes). It also tries a cleaned copy of the text with politeness removed ("hey assistant, can you ... please") and a copy with a mistyped first verb repaired ("clse" becomes "close"). A hit gives an intent and slots, with certainty |
| 5 | `registry.predict` | Only if no rule fired. The active intent model reads the text and returns the best intent, its confidence (0 to 1), and the gap between first and second place |
| 6 | `engine._process` | Decides whether to trust the model. If confidence is below the threshold (tau) or the gap is under 0.10, it does not guess a tool. A plain knowledge question goes to the general-answer path; other low-confidence text uses the agent if one is enabled, else says "I cannot do that yet". A "general override" also sends a text to general answering when the model picked a tool intent (such as system status) but the text contains no word supporting it |
| 7 | `engine._model_slots` | Fills the details the model cannot give: file name, folder name, app name, URL, voice action |
| 8 | `engine._dispatch` | Checks the mode (Chat mode refuses action intents and offers Cowork), then runs the handler for the intent |
| 9 | `tools/*` through `safety/policy.run_guarded` | The handler calls a tool. The gateway authorises it (Part G). For "delete old.txt" the level is L2, so the first call returns "needs confirmation" and no file is touched |
| 10 | `engine._confirm_reply` and `pages/chat.py` | The engine stores the pending action and returns a confirmation question. The page shows a Confirm and Cancel card |
| 11 | You press Confirm | `engine.confirm` re-runs the tool with the one-time token. The file goes to the Recycle Bin (`send2trash`) |
| 12 | `responses.t` | The reply text comes from a template in your language: "File deleted: ..." |
| 13 | `engine.handle_message` | Saves the reply with its intent, confidence and time taken, returns it plus any UI hint (open a page, a voice command) |
| 14 | `pages/chat.py` | Redraws the chat. If voice replies are on, the reply text (stripped of markdown and links, limited to about 500 characters) is sent to the browser to be spoken |

### D2. The order of trust

An analogy: a receptionist first looks at a printed list of exact instructions (rules), then asks the experienced colleague who guesses from past cases (the model), and only then, if allowed, phones an outside expert (a language model). Each step is slower, less certain and less private than the one before, so they are tried in that order.

### D3. Where the three kinds of answer come from

| Kind | Examples | Needs internet |
|---|---|---|
| Rule | "what is 7*8", "open notepad", "remember that ...", "stop listening" | No |
| Model-chosen tool | "ek nayi file ideas.txt bana do" | No |
| General answer | "why is the ocean salty" | Only if Groq, Gemini or Wikipedia is used; Ollama stays on the laptop; with nothing configured you get a web-search link |

---

## Part E. The models

A **model** here means a program that learned a skill from examples instead of being given step-by-step instructions. **Training** is the learning phase; **inference** (or prediction) is using what was learned.

### E1. Terms used in this part

| Term | Plain meaning |
|---|---|
| Intent | What the user wants, as one label such as `app_open` |
| TF-IDF | A way to turn a sentence into numbers. Words that are frequent in a sentence but rare across all sentences count more ("notepad" matters more than "please") |
| n-gram | A run of N neighbouring pieces. Word 2-grams are word pairs; character n-grams (here 2 to 5 letters) catch spelling variants such as "kholo" and "kholdo" |
| Logistic regression | A simple model that adds up weighted evidence for each label and turns the totals into probabilities |
| SVM (support vector machine) | A model that finds the best dividing lines between labels. "Linear" means straight lines. It does not give probabilities by itself, so it is "calibrated": a small extra step converts its scores into probabilities |
| MLP (multi-layer perceptron) | A small neural network: layers of numbers that are adjusted during training |
| Epoch | One pass over all training examples |
| Dropout | Randomly switching off part of a neural network during training so it does not just memorise |
| Validation, test split | Parts of the data held back. Validation is used to choose settings and the best model; test is used only to report a score |
| Accuracy | Share of sentences labelled correctly |
| Macro-F1 | A score from 0 to 1 that averages how well each intent is found, giving every intent equal weight, so a rare intent counts as much as a common one. It is stricter than accuracy |
| Confidence | The model's probability for its top answer |
| tau | The confidence threshold. Below it, the assistant does not act on the model's guess |
| Confusion matrix | A grid showing which intents are mistaken for which |
| Pretrained | Already trained by someone else on a large dataset; used as delivered |

### E2. The intent classifier family (the "understanding" models)

**What they do.** Read one sentence and choose one of 28 intents (the list is in `nlu/dataset.py`). Two intents, maths and thanks/goodbye, are only produced by rules.

**Shared input.** Every model uses the same features (`nlu/features.py`): TF-IDF of words (single words and pairs) joined with TF-IDF of characters (2 to 5 letters inside word edges). The tokenizer splits only on spaces and punctuation, so Hindi and Gujarati vowel signs stay inside their words.

**Why TF-IDF and not a big language model.** The labels are few, the sentences are short, the laptop has no graphics card, and the project goal was small, quick, offline and explainable. A TF-IDF model answers in about 3 to 20 milliseconds.

**Training data.** `data/intents.csv`: 3,143 rows, 28 intents, five language styles (English 877, Hinglish 591, Gujlish 568, Hindi 554, Gujarati 553). Rows are produced by `nlu/dataset.py` from hand-written templates with slot words (file names, app names, topics), then varied with polite prefixes and suffixes and random lower-casing. Later rounds added broader general-knowledge questions and the vision, performance and voice intents. **Every row is marked "unreviewed": no native speaker has checked the Hindi or Gujarati.** Sentences you correct in the chat or add in Model Lab are stored as author or corrected rows.

**How training works** (`nlu/train.py`): shuffle with a fixed seed (42) and split 70 percent train, 15 percent validation, 15 percent test, keeping each intent's share equal in each part. Train each model on the training part. Score on validation, test and the code-mixed file. Tune tau on validation: the smallest value, between 0.30 and 0.90, where the answers above it are at least 97 percent correct while at least 80 percent of messages still get an answer. Choose the model with the highest validation macro-F1 as the active one. Save to `models/` and record everything in the database.

| Model | Setup | Why it was chosen |
|---|---|---|
| M1 TF-IDF + Logistic Regression | `C=20`, up to 2,000 iterations | Fast, small, gives real probabilities, easy to explain; the baseline |
| M3 TF-IDF + calibrated linear SVM | `LinearSVC C=1`, sigmoid calibration with 3 folds | Often the strongest linear text classifier. It replaced a planned embedding model to avoid a large download |
| M2 TF-IDF + PyTorch MLP | one hidden layer of 256 units, ReLU, dropout 0.3, AdamW (learning rate 0.001), at most 60 epochs, stops early after 5 epochs without validation improvement | Shows a small neural network for comparison; CPU only |

**Latest measured results** (from `docs/RESULTS.md`, last run for each model; in-sandbox timings on the author's machine):

| Model | Active | Validation macro-F1 | Test accuracy | Test macro-F1 | Code-mixed macro-F1 | tau | File size | p95 time |
|---|---|---|---|---|---|---|---|---|
| Logistic Regression | no | 0.922 | 0.932 | 0.891 | 0.901 | 0.35 | 3.9 MB | 4.7 ms |
| PyTorch MLP | no | 0.911 | 0.930 | 0.889 | 0.914 | 0.55 | 16.6 MB | 8.4 ms |
| Calibrated SVM | yes | 0.937 | 0.930 | 0.886 | 0.900 | 0.40 | 10.9 MB | 18.1 ms |

Per-language test macro-F1 for the active SVM: English 0.860, Hindi 0.823, Gujarati 0.711, Hinglish 0.807, Gujlish 0.906.

**Honest reading of these numbers.**

- The three models are statistically tied. Differences of 0.005 are within the noise of a test set of about 470 sentences spread over 28 intents. The SVM was chosen by the validation rule, not because it is clearly better.
- The test split is **optimistic**: it comes from the same templates as training. The code-mixed file uses different wording, but it was also written by the same author, and it is small (182 rows).
- Gujarati is the weakest language (0.71). The data is unreviewed, and the pool of Gujarati templates is small.
- Scores went down from 0.921 (earlier, 18 intents) to about 0.89 (now, 28 intents). More classes make the same test harder; this is not a bug.
- The earlier code-mixed figure of 0.640 was a measuring artefact (seven intents had no test rows and counted as zero). It was fixed, and the figure is now about 0.90.
- Real users will write things the templates never imagined. Expect lower accuracy on real text. The assistant protects itself with rules first, the confidence threshold, the gap rule and the safety gateway.

**The 399-sentence evaluation** (`tests/eval/`): a separate set of fresh sentences in 13 sections (identity, memory, files, apps, system status, screenshot, time and date, maths, documents, general questions, vision, performance, voice) and five languages, run through the full engine with every tool faked. Latest result: 398 of 399 pass. The first run, before fixes, passed 256 of 399 (64 percent). **Caveat:** the rules were written while reading the failures, so this set is now a regression check (it catches new breakage) rather than a blind test. None of its sentences is in the training file; the runner checks this every time.

### E3. Object detection models

| Model | What it is | Why chosen | Training and numbers |
|---|---|---|---|
| YOLOv8 n, s, m (Ultralytics) | "You Only Look Once" detectors: look at the whole picture once and output boxes with labels. Sizes n (about 6 MB), s (about 22 MB), m (larger). The page calls them Fast, Balanced, Accurate | Free, fast on a CPU, well known | **Pretrained, not trained here.** They know the 80 COCO classes (person, car, cup, laptop, and so on). Published COCO scores from Ultralytics are about 37 (n), 45 (s) and 50 (m) mAP; these are the vendor's figures, not measured in this project |
| YOLOv8n-cls | A classifier for the 1,000 ImageNet categories | Used as a fallback when nothing is detected and for the "also name other things" option | Pretrained |
| YOLO-World (yolov8s-worldv2) | An "open-vocabulary" detector: you type the words to look for and it uses a text model (CLIP) to match them | Lets the user look for things outside the 80 classes | Pretrained; needs the weights (about 26 MB) and the CLIP text encoder (about 350 MB). **Never downloaded or run in this project, so it is untested.** Less reliable than the standard detector |

Extra logic in `vision/detector.py`: tiled detection runs the model on the whole picture plus overlapping tiles and merges duplicates with non-maximum suppression (keep the most confident of overlapping boxes), which helps small objects.

### E4. Language models and lookups (optional, off by default)

| Service | What it is | When used | Notes |
|---|---|---|---|
| Ollama | A program that runs open language models on your own computer (default name `llama3.2:3b`, a model of roughly 2 GB) | General answers, no key, no consent, nothing leaves the laptop | Not installed or tested here |
| Groq | A cloud service running open models (default `llama-3.1-8b-instant`) | Only with a key and the consent box ticked | Never called with a real key in this project |
| Gemini | Google's cloud model (default `gemini-3.5-flash-lite`) and an embedding model (`gemini-embedding-001`) used for document search | Only with a key and consent | Never called with a real key. Default model names were taken from vendor documentation checked on 2026-11-06 and are editable in Settings because names change |
| Wikipedia | Not a model: a free encyclopedia web service | Fallback for factual questions when consent is on but no model is configured; also optional descriptions on the vision page | The question text is sent to wikipedia.org, so it needs consent |

All of these are free to try: Ollama is free software; Groq and Gemini have free tiers with limits; Wikipedia is free. Cloud answers are limited to 1,024 tokens (roughly 700 words) with a 25-second wait, and identical prompts are cached.

---

## Part F. The database

**SQLite** is a database that lives in one ordinary file (`data/adhyaksh.db`). No server is needed. Think of it as a set of spreadsheets (called tables) in one workbook. The code in `adhyaksh/db.py` is the only code that opens it. It uses write-ahead logging (a safer way to write that survives a crash) and enforces links between tables ("foreign keys"). Changes to the table layout are applied as numbered migrations.

| Table | What each row is | Main columns |
|---|---|---|
| `profile` | The one operator's name | `display_name` |
| `settings` | One setting | `key`, `value` (for example `cloud_consent`, `theme`, `confidence_threshold`, `voice_handsfree`) |
| `conversations` | One conversation | `title`, `created_at` |
| `messages` | One chat message | `conversation_id`, `role` (user or assistant), `content`, `intent`, `confidence`, `latency_ms` |
| `memory_facts` | One remembered fact | `fact`, `category` (personal or general), timestamps |
| `documents` | One indexed file | `filename`, `filepath`, `pages`, `status` |
| `doc_chunks` | One piece of a document | `document_id`, `chunk_index`, `page_or_section`, `text`, `embedding` (only when Gemini embeddings are used), `method` |
| `audit_log` | One action attempt | `ts`, `user_text`, `intent`, `action`, `target`, `level`, `confirmed`, `result` |
| `model_registry` | One trained model | `name`, `kind`, `path`, `dataset_hash`, `is_active` |
| `eval_runs` | One scoring of a model | `accuracy`, `macro_f1`, per-language and confusion data (stored as JSON text), size, speed |
| `feedback` | One "Wrong intent?" correction | `message_id`, `correct_intent`, `note` |

Special rules: deleting a conversation also deletes its messages, and deleting a document deletes its chunks. The audit table has two triggers (automatic guards) that abort any UPDATE or DELETE, so history cannot be rewritten. API keys are never stored here. "Delete all my data" in Settings removes the database file. "Export my data" gives you a copy of it. A command-line backup exists: `python -m adhyaksh.db backup`.

---

## Part G. Safety: levels L0 to L3, confirmation and audit

### G1. The idea

An analogy: every request to touch the computer must pass a security desk. The desk reads a card (the action type), looks up its risk level, checks the destination against a list of allowed places, may ask you to countersign, and stamps a visitor book (the audit log). No tool is allowed to skip the desk: in the code the single function `run_guarded` in `safety/policy.py` is the only way tools run.

### G2. The four levels

| Level | Meaning | Examples in this project | What happens |
|---|---|---|---|
| L0 | Read only | list, read and search files; read memory; ask about documents; system status; PC stats; detect objects in an attached image; show a page | Runs immediately |
| L1 | Reversible | create a file or folder, append to a file, create Excel or Word, open an app, save a memory, take a screenshot, open a website or special folder, change a voice setting | Runs immediately, but folder rules still apply |
| L2 | Destructive or hard to undo | overwrite or delete a file, close an app, delete a memory, clean temp files, run Python in Power mode | **Needs your confirmation** first |
| L3 | Never allowed | running shell commands; any action type not known to the system | Refused, and the refusal is logged |

### G3. The checks, in order

1. The action must be a known type; unknown types are L3.
2. For file actions, the path is resolved to its real location and must lie inside one of your **allowed folders** (default: `Documents\ADHYAKSH_Workspace`). Sneaky paths such as `..\secret.txt` are caught because the path is resolved first. System folders (Windows, Program Files, ProgramData), drive roots and your profile root are never allowed, even if you list them.
3. An allowed root itself cannot be deleted or overwritten.
4. For apps, the name must be on the **allow-list** (name to command; no shell is used, so "notepad & del x" cannot run).
5. For L2, the first call returns a one-time **confirmation token** (valid 5 minutes, tied to that exact action and target). The chat page shows a Confirm and Cancel card. Only a matching token lets the second call run. Typing "yes", "haan" or "हाँ" also confirms.
6. The tool runs inside a try block; an unexpected error becomes a clean failure message, not a crash.
7. **Audit rule:** every action ends in exactly one audit row: executed, failed, blocked, rejected or cancelled. Waiting for confirmation is not an action yet and writes nothing.

### G4. Other safety rules in the code

- Maths uses a small parser (`safe_eval`) that accepts only numbers and arithmetic signs; the program never uses `eval` or `exec` on user text.
- Text read from files, web pages or tools is wrapped as data in the agent loop; instructions inside it are not obeyed (a test covers a hostile page trying to trigger a delete).
- Logs hide anything that looks like a key. Keys are read from `.env` or the environment only.
- Cloud use is off until the `cloud_consent` setting is on. Ollama is local, so it needs no consent. Before sending anything outside, the code checks consent, then that a key exists.
- Chat mode versus Cowork mode adds a second layer: in Chat mode all action intents are refused before any tool is reached.
- Voice: the microphone is started only by a click in the browser; the browser asks permission itself. The assistant can request "start listening", but the browser still decides.

---

## Part H. Voice, vision, attachments, and document Q and A

### H1. Voice

**How it works.** The voice strip is a small web page (`voice/component/index.html`) embedded in Chat. It uses the **Web Speech API**, a feature built into Chrome and Edge. Recognition turns microphone sound into text; synthesis reads text aloud. The page sends recognised text back to Python, where it is handled exactly like typed text.

**Modes.**

| Mode | Behaviour |
|---|---|
| Speak once | Listen to one phrase, then stop |
| Hands-free | Keeps listening and restarts itself after each phrase or after speaking |
| Wake word | In hands-free mode, only phrases that start with "Adhyaksh" are acted on. Saying just "Adhyaksh" arms it for 10 seconds |
| Spoken replies | Replies to spoken commands are read aloud; the reply is cleaned of markdown and links and capped near 500 characters. While speaking, recognition pauses so the assistant does not hear itself |
| Voice commands | "stop listening", "be quiet", "read that out loud", "turn on the wake word", "switch voice to Hindi" are understood in all five language styles, either inside the page (stop phrases) or as chat intents that change settings |

**Limits.** It needs Chrome or Edge. In Chrome the actual speech-to-text is done by the browser vendor's online service, so recognition is not offline and your voice audio goes to that service; this is a property of the browser, not of the app. The voice component, hands-free mode and the wake word were **not tested on the target laptop**. Hindi and Gujarati accuracy depends on the browser and installed voices.

### H2. Vision

Two routes lead to the detector (Part E3):

1. **Object Detection page**: camera snapshot or upload, with model size, tiled scan, named objects, and descriptions.
2. **Chat**: attach a JPG, PNG or WEBP photo and the assistant lists objects ("2 cup, laptop"), using the guarded `vision_detect` action (L0). Saying "open the vision page" switches pages.

Safety on images: only JPG, PNG and WEBP are accepted (the file's first bytes are checked, not just its name); the size limit is 10 MB; results are cached by a fingerprint of the image. Detection runs locally; the only optional network use is the Wikipedia description lookup.

### H3. Attachments in Chat

Attach files with the paperclip. What happens next depends on the type:

| Attachment | Result |
|---|---|
| PDF, DOCX, TXT, MD, CSV (up to 25 MB) | Saved into `data/uploads`, split into pieces, stored in the database. The reply says "Indexed: name (N passages)". If your message also contained a question, it is answered from the file at once |
| JPG, PNG, WEBP (up to 10 MB) | Sent to object detection (Part H2) |
| Anything else | Rejected with a reason |

The "Attached documents" box lists indexed files and removes them. The index is shared by all conversations (it is not per conversation).

### H4. Document questions (RAG)

**RAG** means retrieval-augmented generation: first retrieve the relevant text, then use it to answer. The steps:

1. **Read.** PDF with PyMuPDF (page numbers kept), DOCX with python-docx (headings become section names), text files directly.
2. **Chunk.** Cut into pieces of about 500 characters that overlap by 100, on word boundaries, so a sentence cut at one edge appears whole in the next piece.
3. **Store.** Each piece goes into `doc_chunks`.
4. **Retrieve.** For a question, TF-IDF similarity (cosine, with word pairs and a list of ignorable words) scores every piece; the top four are kept. With Gemini consent, embeddings (numbers that capture meaning) are used instead.
5. **Decide.** Pieces scoring under 0.15 (adjustable in Settings) are dropped. If nothing is left, the reply is "Not found in your documents", or the question falls through to general answering.
6. **Answer.** Offline: the best three pieces are shown with "(Source: file, page)". With cloud consent and a key: a language model is told to answer only from those pieces, and the sources are listed.

Caveats: TF-IDF matches words, not meaning, so a paraphrased question can miss. PDF reading and the keyed cloud answer were not tested on the target laptop (DOCX and TXT were tested).

---

## Part I. Libraries, and how to run, test and train

### I1. Libraries and why each was chosen

A **library** is ready-made code you borrow instead of writing. All are free and open source.

| Library | Used for | Why this one |
|---|---|---|
| Python standard library (`sqlite3`, `re`, `ast`, `difflib`, `subprocess`) | Database, text patterns, safe maths, typo matching, launching approved apps | Built in, nothing to install |
| Streamlit | The whole user interface, in Python only | Fastest way to make a working browser UI without writing web code |
| numpy, pandas | Number arrays and tables | Required by the machine-learning tools; pandas reads the training CSV |
| scikit-learn | TF-IDF, logistic regression, SVM, calibration, scoring, train and test splitting | The standard small-model toolkit; runs well on a CPU |
| joblib | Saving and loading trained scikit-learn models | Installed with scikit-learn |
| PyTorch (CPU build) | The MLP neural network | Optional; the project runs without it, and the MLP is skipped if it is missing |
| Ultralytics | YOLOv8 and YOLO-World | Easy loading and running of the detection models; optional, large |
| Pillow | Reading images, drawing boxes, screenshots | The standard Python imaging library |
| psutil | CPU, memory, disk, process list, stopping a started app | Cross-platform system information |
| send2trash | Delete to the Recycle Bin instead of permanent deletion | Makes deletion recoverable |
| openpyxl, python-docx | Creating Excel and Word files, reading Word files | Pure-Python, no Office needed |
| PyMuPDF | Reading PDF text with page numbers | Fast and accurate |
| requests | HTTP calls to Groq, Gemini, Ollama, Wikipedia | Simple and reliable |
| python-dotenv | Reading API keys from `.env` | Keeps keys out of the code |
| matplotlib | The confusion-matrix picture in Model Lab | Standard plotting |
| pytest, pytest-cov | Running the automatic tests and measuring coverage | Standard test tools |

Sizes: measured earlier in a Linux sandbox, numpy 41 MB, pandas 67 MB, scikit-learn 46 MB, scipy 108 MB, matplotlib 34 MB, and the smaller ones a few MB each (about 315 MB together). Streamlit, PyTorch, Ultralytics and PyMuPDF were not measured; PyTorch and Ultralytics are the largest items and are optional. The trained intent models are 4 to 17 MB each; YOLO weights in `models/` are about 6 to 23 MB each. The project's stated target of 1.5 GB or less for everything was an estimate that was **not measured on the target laptop**.

### I2. Run

1. Install Python 3.11 or 3.12 on Windows 10 or 11.
2. Double-click `run.bat` (or run `.\run.bat` in a terminal). It creates a virtual environment, installs `requirements-core.txt`, and starts Streamlit. The browser opens the app. On other systems use `./run.sh`.
3. First visit: enter your name. Chat and the other pages are ready. Optional extras: `pip install torch --index-url https://download.pytorch.org/whl/cpu` for the MLP, `pip install ultralytics` for object detection, Ollama from its own website for local language answers.
4. Optional keys: copy `.env.example` to `.env`, or type a key on the Settings page. Then tick the consent box if you want cloud answers.

Notes: `run.bat` creates a folder named `venv`, while the project notes mention `.venv`; use whichever your install actually created. After changing any imported module, stop Streamlit fully and start it again, because it keeps modules in memory.

### I3. Test

Run all tests except the one known to crash when it finishes on Windows:

`.venv\Scripts\python.exe -m pytest tests/ -q --ignore=tests/test_tools.py`

Run only the tests of a file you changed, for example `python -m pytest tests/test_memory_commands.py -q`. Tests need no internet and no API key; every network call is replaced by a fake and apps are never launched. The 399-sentence evaluation is separate: `python tests/eval/run_eval.py` trains a fresh model in a temporary folder, runs every sentence with all tools faked, and writes `docs/EVAL_REPORT.md` and `tests/eval/results.csv`.

### I4. Train

| Task | Command |
|---|---|
| Check the training file | `python -m adhyaksh.nlu.dataset validate` |
| See balance by intent and language | `python -m adhyaksh.nlu.dataset report` |
| Add extra phrasings (keeps existing rows) | `python -m adhyaksh.nlu.dataset augment` and `augment-knowledge` |
| Train all models and rewrite `docs/RESULTS.md` | `python -m adhyaksh.nlu.train --all` (about 100 seconds on the author's machine) |
| Train from the UI | Model Lab, Training tab |

Training picks the best model by validation score, sets the confidence threshold, and makes that model active. Never train on the evaluation sentences or on `data/test_codemixed.csv`.

---

## Part J. Known limits and honest caveats

### J1. Data and models

- All 3,143 training sentences are synthetic (generated from templates) and unreviewed. No native speaker has checked the Hindi or Gujarati. Gujarati is the weakest language in the scores (macro-F1 about 0.71).
- The held-out test scores share templates with training and are therefore optimistic. Expect lower accuracy on real people's sentences.
- The three intent models are tied within noise. The active one was chosen by a validation rule.
- The 399-sentence evaluation (398 pass) is a regression suite, not a blind test, because rules were tuned while reading its failures. One case is a deliberate non-match: "turn on power mode for speed" is not treated as a performance request because "Power mode" in this app is the dangerous Python-running switch, which is changed only in Settings.
- Number words work for the common words (zero to twenty, the tens, hundred) in English, Hindi and Gujarati; irregular Hindi and Gujarati numbers from 21 to 99 beyond the tens are not understood.
- The standard detector knows only 80 object types. Tiled mode finds smaller instances of those types, not new types. YOLO-World, which accepts any word, was never downloaded or run, so its quality is unknown.
- Document search matches words, not meaning (unless Gemini embeddings are used), so paraphrased questions can miss. The document index is shared by all conversations.
- General answers without Ollama, a cloud key or consent are limited to a Wikipedia summary or a search link.
- Memory recall is keyword overlap, not understanding. "What do you remember" lists up to 20 items.

### J2. Not tested on the target laptop

Voice (recognition, hands-free, wake word, spoken replies), the PyTorch MLP on the target, PDF reading, Recycle Bin deletion with `send2trash`, calls to Groq, Gemini and Ollama with real services, launching Windows applications, a clean install from `run.bat`, the PC Performance page, and the start-up time and total disk size targets.

### J3. Design limits

- One operator, no accounts or passwords. Anyone who can open the browser page on the laptop can use it.
- The browser speech service is online in Chrome, so spoken input is not fully offline.
- Replies from a language model are not streamed word by word from the model itself; the page only reveals finished text gradually.
- Streamlit reruns the page on every click; very long conversations are cut to the last turns that the settings allow (default 8 turns for the model prompt, 50 messages shown).
- The audit log cannot be edited by the app, but "Delete all my data" removes the whole database file, log included.
- Python 3.11 or 3.12 only. Windows is the primary target; some behaviour (Recycle Bin, special folders, app launching) is Windows-specific.

### J4. Documentation drift

Some older files in `docs/` (for example `FILES.md`, `TESTS.md`, `DATA_CARD.md`, `PROGRESS.md`, `CONFIG.md`) were written before several upgrades. They still mention 18 intents, 1,208 training rows, a Documents page, and test files that no longer exist. The code and `docs/RESULTS.md`, `docs/EVAL_REPORT.md` and this guide reflect the current state. `requirements-core.txt` still gives lower bounds only; pinning exact versions with `pip freeze` is on the to-do list in `CLAUDE.md`.

### J5. Glossary of the main terms

| Term | Meaning |
|---|---|
| Intent | The label for what a message asks for |
| Slot | A detail needed to do the intent (file name, app name) |
| Rule layer | Hand-written patterns tried before the model |
| Router | The code file holding the rule layer |
| Engine | The code that decides, calls tools and writes the reply |
| Tool | A piece of code that does something on the computer |
| Gateway | `run_guarded`, the single door every tool call must pass |
| Allow-list | A short list of things that are permitted; everything else is refused |
| Audit log | The permanent record of attempted actions |
| Consent | Your explicit yes to sending data to a cloud service |
| RAG | Find relevant text first, then answer from it |
| Code-mixed | A sentence that mixes languages, such as Hinglish |
| Regression test | A check that old behaviour still works after a change |

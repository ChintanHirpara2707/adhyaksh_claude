# QA log

## Automated (sandbox, 2026-11-07)
python -m pytest equivalent: 76 passed, 0 failed (pytest itself was unavailable; a minimal runner executed the same test functions). Coverage not measured.

## Manual tests (run on the laptop; paste any error text back)
Setup: python -m venv venv, activate, pip install -r requirements-core.txt, pip install torch --index-url https://download.pytorch.org/whl/cpu

1. Unit tests: python -m pytest. Expect all pass. Install pytest-cov and run python -m pytest --cov=adhyaksh to get the coverage number.
2. Train: python -m adhyaksh.nlu.train --all. Expect three models listed, M2 included, no skip message. Record macro-F1 values.
3. Start: streamlit run app.py. Time from command to first screen (target 15 s).
4. J1 first run: open Chat. Expect a form asking for name and folder. Enter both, press Save. Expect the chat view.
5. J2 chat: send "hello", "2+2*3", "I am your new user Chintan", "what is my name". Expect replies without errors.
6. J3 memory: "remember that my car is Audi", then "what is my car?". Expect "Your car is Audi." Open Memory: the fact is listed; edit and delete work.
7. J4 documents: Documents page, upload a PDF, a DOCX and a TXT. Ask a question: expect an answer with file and page or section. Ask an unrelated question: expect "Not found in your documents." Time a 20-page PDF (target under 30 s).
8. J5 delete: "create notes.txt", "delete it". Expect a confirmation card. Press Confirm. Check the Recycle Bin contains notes.txt. Activity page shows the rows.
9. Excel: "open Excel and write 5 Indian names in 5 rows". Expect names.xlsx opens with 5 names in A1 to A5.
10. Applications: Tools page, open Notepad and Calculator; close one (confirmation card). In chat "open regedit": expect a refusal.
11. J6 Model Lab: Training tab, press Train all models, watch progress, chat stays usable. Comparison tab shows the table and confusion matrix. Dataset tab: add an example, retrain.
12. J7 dashboard: check accuracy, macro-F1, per-language F1, latency and size columns.
13. J8 theme: toggle Dark mode on every page including Model Lab confusion matrix; reload; choice persists.
14. Voice (Chrome or Edge): in Chat press Start listening for English, Hindi, Gujarati. Say a short command. Expect the transcript to appear as a message and be answered. Turn on "Speak replies aloud" in Settings and check replies are spoken. Record per language: works, no voice installed, or error text.
15. Settings: save folders (try a system folder: expect a refusal), change threshold, export data, run Delete all my data.
16. LLM (only with a key): Settings, choose provider, paste key, tick consent; ask "what is the capital of France". Expect an answer. Untick consent: expect the web search link message.
17. Widths and keyboard: browser at 390 px wide; Tab through the Chat page. Hindi and Gujarati text renders without boxes.
18. Footprint: size of the venv folder plus models plus data folder (target 1.5 GB or less) and update docs/PERFORMANCE.md.
19. Clean install: unzip adhyaksh_final.zip in a new folder, run run.bat, confirm the app starts.

## Results log
| Date | Check | Result |
|------|-------|--------|
| 2026-11-07 | Automated suite in sandbox | 76 passed |
| 2026-11-06 | P1 shell (author) | passed: 7 pages, theme toggle persists |

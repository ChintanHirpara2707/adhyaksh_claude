# Performance and footprint (measured in the build sandbox, Linux, Python 3.12, CPU)

| Measure | Result | Target | Note |
|---|---|---|---|
| Intent prediction p95 (single text, model in memory) | 1.5 ms (M1), 7.4 ms (M3) | under 300 ms | from docs/RESULTS.md |
| Chat message p95, non-LLM (rules, model, tool, SQLite writes) | about 10 to 12 ms, median about 8 ms | under 1 s | tests/test_chat.py, 60 messages |
| System status call | about 210 ms (CPU sample interval 0.2 s); cached for 5 s | under 1 s | |
| Import engine, load model, first prediction | 1.17 s | | excludes Streamlit |
| Training M1 + M3 | 3.3 s total | under 10 min | M2 not run here |
| DOCX indexing, 166 passages | 0.07 s | 20-page PDF under 30 s | PDF path NOT TESTED (PyMuPDF missing) |
| Cold start to first screen | NOT MEASURED | 15 s or less | Streamlit not installed in sandbox |
| Footprint of full environment | NOT MEASURED | 1.5 GB or less | see below |

## Footprint
Measured package sizes in the sandbox: numpy 41 MB, pandas 67 MB, scikit-learn 46 MB, scipy 108 MB, matplotlib 34 MB, lxml 12 MB, joblib 2 MB, python-docx 2 MB, openpyxl 2 MB, psutil 1 MB (about 315 MB). Not installed here, so NOT MEASURED: streamlit, CPU PyTorch, PyMuPDF, send2trash. The project source is under 1 MB, data 120 KB, trained models about 5 MB. The P0 estimate of 1.0 to 1.2 GB total remains an estimate until measured on the target laptop (command: see docs/QA_LOG.md).

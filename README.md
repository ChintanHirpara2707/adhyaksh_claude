# ADHYAKSH

Private, local-first, multilingual (English, Hindi, Gujarati, code-mixed) desktop assistant.
Status: v0.7.0, all Tier A phases built. See docs/PROGRESS.md for what is verified and what is UNTESTED ON TARGET.

## Requirements
Windows 10/11 (primary), Python 3.11, about 1.5 GB free disk.

## Install and run
Windows: double-click run.bat. Others: ./run.sh
Manual: python -m venv venv, activate it, pip install -r requirements-core.txt, streamlit run app.py

## Train the intent models
python -m adhyaksh.nlu.dataset validate
python -m adhyaksh.nlu.train --all
This also rewrites docs/RESULTS.md. Install CPU PyTorch first to include the MLP model:
pip install torch --index-url https://download.pytorch.org/whl/cpu

## Tests
python -m pytest

## Database backup
python -m adhyaksh.db backup

## API keys
Optional. Copy .env.example to .env and fill in a key, or enter it in Settings. The app works without any key. Cloud use (sending questions or document passages to a provider) is OFF until you grant consent in Settings.

## Known limitations
See docs/PROGRESS.md.

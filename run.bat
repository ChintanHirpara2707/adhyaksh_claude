@echo off
cd /d "%~dp0"
if not exist venv (
  py -3.11 -m venv venv || python -m venv venv
  call venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements-core.txt
) else (
  call venv\Scripts\activate.bat
)
streamlit run app.py

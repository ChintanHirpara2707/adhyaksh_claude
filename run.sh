#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
if [ ! -d venv ]; then
  python3 -m venv venv
  . venv/bin/activate
  python -m pip install --upgrade pip
  pip install -r requirements-core.txt
else
  . venv/bin/activate
fi
streamlit run app.py

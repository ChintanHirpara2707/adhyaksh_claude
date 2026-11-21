@echo off
cd /d "%~dp0"
if not exist venv (
  py -3.12 -m venv venv || py -3.11 -m venv venv || python -m venv venv
  call venv\Scripts\activate.bat
  python -m pip install --upgrade pip
  pip install -r requirements-core.txt
) else (
  call venv\Scripts\activate.bat
)
rem Train the intent models once when there are none yet (a fresh clone, or a new data folder). No PyTorch is
rem needed: that model is skipped and the other two are trained.
set NEED_TRAIN=
if not exist models\m3_svm.joblib set NEED_TRAIN=1
if not exist data\adhyaksh.db set NEED_TRAIN=1
if defined NEED_TRAIN (
  echo Training the intent models once. This takes a few minutes.
  python -m adhyaksh.nlu.train --all || echo Training failed. The app still starts; train later from the Model Lab page.
)
streamlit run app.py

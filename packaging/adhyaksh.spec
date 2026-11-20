# PyInstaller spec for a one-folder Windows build of ADHYAKSH.
#
# Build (from the project folder, inside the virtual environment):
#     pip install pyinstaller
#     pyinstaller packaging/adhyaksh.spec --noconfirm
# Result: dist/ADHYAKSH/ADHYAKSH.exe (start it; the browser opens at http://localhost:8501).
#
# Not included on purpose: the .env file (API keys), the database, logs, uploads and downloaded models.
# Optional parts (PyTorch, Ultralytics, faster-whisper, fastembed, RapidOCR) are bundled only if they are
# installed in the environment that builds; the app works without them.
# -*- mode: python ; coding: utf-8 -*-
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent

datas = [
    (str(ROOT / "app.py"), "."),
    (str(ROOT / "app_pages"), "app_pages"),
    (str(ROOT / "adhyaksh"), "adhyaksh"),
    (str(ROOT / ".streamlit"), ".streamlit"),
    (str(ROOT / "data" / "intents.csv"), "data"),
    (str(ROOT / "data" / "test_author.csv"), "data"),
    (str(ROOT / "data" / "test_codemixed.csv"), "data"),
    (str(ROOT / ".env.example"), "."),
]
binaries = []
hiddenimports = collect_submodules("adhyaksh")

for pkg in ["streamlit", "sklearn", "fitz", "docx", "openpyxl", "send2trash", "psutil"]:
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
datas += copy_metadata("streamlit")

for optional in ["ultralytics", "faster_whisper", "ctranslate2", "fastembed", "rapidocr_onnxruntime", "onnxruntime"]:
    if importlib.util.find_spec(optional) is not None:
        d, b, h = collect_all(optional)
        datas += d
        binaries += b
        hiddenimports += h

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tkinter.test", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="ADHYAKSH", console=True, upx=False)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="ADHYAKSH")

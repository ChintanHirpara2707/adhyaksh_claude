"""Entry point of the packaged Windows build (PyInstaller): starts the Streamlit app and opens the browser.

User data (database, logs, uploads) and downloaded models live next to ADHYAKSH.exe in the folders
"data" and "models", so they survive updates of the program files. Nothing is sent online by starting the app.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> int:
    frozen = getattr(sys, "frozen", False)
    exe_dir = Path(sys.executable).resolve().parent if frozen else Path(__file__).resolve().parent.parent
    bundle = Path(getattr(sys, "_MEIPASS", exe_dir))
    os.environ.setdefault("ADHYAKSH_DATA_DIR", str(exe_dir / "data"))
    os.environ.setdefault("ADHYAKSH_MODELS_DIR", str(exe_dir / "models"))
    os.environ.setdefault("YOLO_AUTOINSTALL", "false")
    # The training data ships inside the bundle; copy it once so the Model Lab can add examples.
    data = Path(os.environ["ADHYAKSH_DATA_DIR"])
    data.mkdir(parents=True, exist_ok=True)
    for name in ("intents.csv", "test_author.csv", "test_codemixed.csv"):
        src, dst = bundle / "data" / name, data / name
        if src.exists() and not dst.exists():
            dst.write_bytes(src.read_bytes())
    os.chdir(bundle)
    from streamlit.web import cli as stcli

    sys.argv = ["streamlit", "run", str(bundle / "app.py"), "--global.developmentMode=false",
                "--server.headless=false", "--browser.gatherUsageStats=false", "--server.address=127.0.0.1"]
    return stcli.main()


if __name__ == "__main__":
    sys.exit(main())

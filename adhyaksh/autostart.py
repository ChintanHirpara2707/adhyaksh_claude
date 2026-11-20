"""Start the background engine when Windows starts (optional, the user turns it on in Settings).

A small command file in the user's own Startup folder runs `pythonw -m adhyaksh.server` minimised from the project
folder. No administrator rights, no Windows service, no registry change; turning it off deletes the file. Nothing
here runs on its own: only the Settings page calls enable() or disable().
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED, E_UNSUPPORTED_OS, Result

FILE_NAME = "ADHYAKSH engine.cmd"


def startup_folder() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def _python() -> Path:
    exe = Path(sys.executable)
    windowless = exe.with_name("pythonw.exe")
    return windowless if windowless.exists() else exe


def script() -> str:
    root = config.ROOT
    return ("@echo off\r\n"
            "rem Starts the ADHYAKSH background engine (127.0.0.1 only). Delete this file to stop it starting.\r\n"
            f'cd /d "{root}"\r\n'
            f'start "" /min "{_python()}" -m adhyaksh.server\r\n')


def enabled() -> bool:
    return (startup_folder() / FILE_NAME).exists()


def enable() -> Result:
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Starting with Windows works on Windows only.")
    folder = startup_folder()
    if not folder.is_dir():
        return Result.failure(E_ACTION_FAILED, "The Windows Startup folder was not found.")
    (folder / FILE_NAME).write_text(script(), encoding="utf-8")
    return Result.success({"path": str(folder / FILE_NAME)})


def disable() -> Result:
    path = startup_folder() / FILE_NAME
    if path.exists():
        path.unlink()
    return Result.success({"path": str(path)})

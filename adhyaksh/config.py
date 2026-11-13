"""Paths, constants and the settings loader (values stored in SQLite)."""
from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

APP_NAME = "ADHYAKSH"
ROOT = Path(__file__).resolve().parent.parent


def _ensure(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def data_dir() -> Path:
    return _ensure(Path(os.environ.get("ADHYAKSH_DATA_DIR") or ROOT / "data"))


def db_path() -> Path:
    return data_dir() / "adhyaksh.db"


def uploads_dir() -> Path:
    return _ensure(data_dir() / "uploads")


def logs_dir() -> Path:
    return _ensure(data_dir() / "logs")


def backups_dir() -> Path:
    return _ensure(data_dir() / "backups")


def models_dir() -> Path:
    return _ensure(Path(os.environ.get("ADHYAKSH_MODELS_DIR") or ROOT / "models"))


def default_workspace() -> Path:
    return Path.home() / "Documents" / "ADHYAKSH_Workspace"


def default_app_allowlist() -> dict[str, list[str]]:
    """Allow-listed applications: name -> command list (never run through a shell)."""
    if os.name == "nt":
        cands = {
            "notepad": ["notepad.exe"], "calculator": ["calc.exe"], "paint": ["mspaint.exe"],
            "snipping tool": ["SnippingTool.exe"], "file explorer": ["explorer.exe"],
            "chrome": ["chrome.exe"], "edge": ["msedge.exe"], "brave": ["brave.exe"],
            "vs code": ["code"], "whatsapp": ["WhatsApp.exe"], "spotify": ["Spotify.exe"],
        }
    elif sys.platform == "darwin":
        cands = {"calculator": ["open", "-a", "Calculator"], "chrome": ["open", "-a", "Google Chrome"],
                 "vs code": ["code"]}
    else:
        cands = {"calculator": ["gnome-calculator"], "chrome": ["google-chrome"], "vs code": ["code"],
                 "notepad": ["gedit"]}
    if os.name == "nt":
        return cands  # Windows resolves these through PATH and App Paths at launch time
    return {k: v for k, v in cands.items() if shutil.which(v[0])}


def default_special_folders() -> dict[str, str]:
    """Windows special folders: friendly name -> shell command or user-profile subfolder."""
    if os.name != "nt":
        return {}
    home = str(Path.home())
    return {
        "recycle bin": "shell:RecycleBinFolder",
        "downloads": str(Path.home() / "Downloads"),
        "documents": str(Path.home() / "Documents"),
        "desktop": str(Path.home() / "Desktop"),
        "explorer": "explorer.exe",
    }


DEFAULTS: dict[str, str] = {
    "theme": "",  # "" = never chosen (follow OS on first visit), else "light" or "dark"
    "confidence_threshold": "0.60",
    "conversation_turns": "8",
    "active_model": "",
    "cloud_consent": "false",
    "voice_reply": "false",
    "llm_provider": "",
    "allowed_folders": json.dumps([str(default_workspace())]),
    "default_work_folder": str(default_workspace()),
    "app_allowlist": json.dumps(default_app_allowlist()),
    "embedding_model": "gemini-embedding-001",  # per Google docs, checked 2026-11-06; editable in Settings
    "groq_model": "llama-3.1-8b-instant",  # per Groq docs, checked 2026-11-06; editable in Settings
    "gemini_model": "gemini-3.5-flash-lite",  # per Google docs, checked 2026-11-06; editable in Settings
    "ollama_model": "llama3.2:3b",  # local model name for the optional Ollama provider
    "doc_min_score": "0.15",
    "power_mode": "false",
    "vision_model": "balanced",
    "vision_imgsz": "640",
}


def get(key: str) -> str:
    from adhyaksh import db

    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting: {key}")
    value = db.get_setting(key)
    return DEFAULTS[key] if value is None else value


def set_value(key: str, value: str) -> None:
    from adhyaksh import db

    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting: {key}")
    db.set_setting(key, str(value))


def get_float(key: str) -> float:
    return float(get(key))


def get_bool(key: str) -> bool:
    return get(key).strip().lower() == "true"


def get_allowed_roots() -> list[Path]:
    """Allowed root folders as resolved paths (may not exist yet)."""
    try:
        raw = json.loads(get("allowed_folders"))
    except json.JSONDecodeError:
        raw = []
    return [Path(r).expanduser().resolve() for r in raw if str(r).strip()]


def configure_folders(paths: list[str], default: str) -> tuple[bool, str]:
    """Validate and save allowed folders and the default work folder. Returns (ok, message)."""
    from adhyaksh.safety import policy

    roots = []
    for raw in paths:
        if not raw.strip():
            continue
        p = Path(raw.strip()).expanduser().resolve()
        if policy.is_system_path(p):
            return False, f"{p} is a system folder and cannot be an allowed folder."
        roots.append(p)
    if not roots:
        return False, "Add at least one allowed folder."
    d = Path(default.strip() or str(roots[0])).expanduser().resolve()
    if not any(policy.is_within(d, r) for r in roots):
        return False, "The default work folder must be inside an allowed folder."
    for r in roots:
        r.mkdir(parents=True, exist_ok=True)
    set_value("allowed_folders", json.dumps([str(r) for r in roots]))
    set_value("default_work_folder", str(d))
    return True, "Folders saved."

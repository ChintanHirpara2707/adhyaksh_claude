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
    "agent_mode": "auto",  # "auto": use the tool-calling agent whenever a language model is available; "off": rules only
    "voice_reply": "false",
    "voice_handsfree": "false",  # start listening automatically and speak replies to spoken commands
    "voice_wake_word": "false",  # in hands-free mode, only act on phrases that start with "Adhyaksh"
    "voice_lang": "en-IN",  # speech recognition and spoken-reply language
    "stt_engine": "browser",  # "browser": the browser's speech recognition; "local": faster-whisper on this laptop
    "stt_model": "base",  # local speech model size: tiny, base or small
    "tts_rate": "1.0",  # spoken-reply speed, 0.6 to 1.6
    "tts_voice": "",  # preferred browser voice name; empty = best available for the language
    "voice_barge_in": "true",  # stop speaking when the user starts talking
    "wake_words": "adhyaksh, adhyaksha, adyaksh, hey assistant",  # extra wake words, comma separated
    "llm_provider": "",
    "allowed_folders": json.dumps([str(default_workspace())]),
    "default_work_folder": str(default_workspace()),
    "app_allowlist": json.dumps(default_app_allowlist()),
    "embedding_model": "gemini-embedding-001",  # per Google docs, checked 2026-11-06; editable in Settings
    "groq_model": "llama-3.1-8b-instant",  # per Groq docs, checked 2026-11-06; editable in Settings
    "gemini_model": "gemini-3.5-flash-lite",  # per Google docs, checked 2026-11-06; editable in Settings
    "ollama_model": "llama3.2:3b",  # local model name for the optional Ollama provider
    "openai_compat_url": "http://127.0.0.1:1234/v1",  # any OpenAI-compatible server; loopback counts as local
    "openai_compat_model": "",
    "llm_tool_mode": "auto",  # auto: native tool calls when the model supports them, else the JSON protocol
    "routing": "local_first",  # local_first: complete single commands run here without a model round trip
    "llm_json_only_models": "[]",  # learned at run time: models that rejected native tool calls
    "doc_min_score": "0.15",
    "doc_min_score_embed": "0.35",  # minimum cosine similarity when embeddings are used for document search
    "active_notebook": "1",  # notebook that receives attachments and answers document questions
    "embeddings_local": "auto",  # "auto": use the local embedding model when its files are present; "off": never
    "embedding_local_model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    "power_mode": "false",
    "vision_model": "balanced",
    "vision_imgsz": "640",
}


# ---------------------------------------------------------------------------
# Validation: every setting has a type. Wrong types and unknown choices are rejected when saved; numbers
# outside their range are clamped; a bad value already in the database is ignored (the default is used).
# ---------------------------------------------------------------------------
_BOOL = ("bool",)
RULES: dict[str, tuple] = {
    "theme": ("choice", {"", "light", "dark"}),
    "confidence_threshold": ("float", 0.0, 1.0),
    "conversation_turns": ("int", 1, 50),
    "cloud_consent": _BOOL, "voice_reply": _BOOL, "voice_handsfree": _BOOL, "voice_wake_word": _BOOL,
    "voice_barge_in": _BOOL, "power_mode": _BOOL,
    "agent_mode": ("choice", {"auto", "off"}),
    "voice_lang": ("choice", {"en-IN", "hi-IN", "gu-IN"}),
    "stt_engine": ("choice", {"browser", "local"}),
    "stt_model": ("choice", {"tiny", "base", "small"}),
    "tts_rate": ("float", 0.6, 1.6),
    "llm_provider": ("choice", {"", "groq", "gemini", "ollama", "openai_compat"}),
    "llm_tool_mode": ("choice", {"auto", "native", "json"}),
    "routing": ("choice", {"local_first", "llm_first"}),
    "llm_json_only_models": ("json", list),
    "openai_compat_url": ("url",),
    "allowed_folders": ("json", list),
    "app_allowlist": ("json", dict),
    "doc_min_score": ("float", 0.0, 1.0),
    "doc_min_score_embed": ("float", 0.0, 1.0),
    "active_notebook": ("int", 1, 10**9),
    "embeddings_local": ("choice", {"auto", "off"}),
    "vision_model": ("choice", {"fast", "balanced", "accurate"}),
    "vision_imgsz": ("int", 160, 1920),
}


class SettingError(ValueError):
    """A setting value of the wrong type or outside its allowed choices."""


def normalize(key: str, value) -> str:
    """The value as it will be stored, or SettingError with a plain explanation."""
    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting: {key}")
    text = str(value).strip() if not isinstance(value, bool) else ("true" if value else "false")
    rule = RULES.get(key)
    if rule is None:
        return str(value)
    kind = rule[0]
    if kind == "bool":
        if text.lower() not in ("true", "false"):
            raise SettingError(f"{key} must be true or false, not '{text}'.")
        return text.lower()
    if kind in ("float", "int"):
        try:
            num = float(text)
        except ValueError:
            raise SettingError(f"{key} must be a number, not '{text}'.") from None
        if num != num:  # NaN
            raise SettingError(f"{key} must be a number.")
        clamped = min(rule[2], max(rule[1], num))
        if kind == "int":
            return text if clamped == num and text.lstrip("-").isdigit() else str(int(round(clamped)))
        return text if clamped == num else f"{clamped:g}"
    if kind == "choice":
        if text not in rule[1]:
            raise SettingError(f"{key} must be one of: {', '.join(sorted(c or '(empty)' for c in rule[1]))}.")
        return text
    if kind == "url":
        from urllib.parse import urlparse
        u = urlparse(text)
        if u.scheme not in ("http", "https") or not u.hostname:
            raise SettingError(f"{key} must be an http or https address, for example http://127.0.0.1:1234/v1.")
        return text
    if kind == "json":
        try:
            parsed = json.loads(text)
        except ValueError:
            raise SettingError(f"{key} must be valid JSON.") from None
        if not isinstance(parsed, rule[1]):
            raise SettingError(f"{key} must be a JSON {'list' if rule[1] is list else 'object'}.")
        return str(value)
    return str(value)


def get(key: str) -> str:
    from adhyaksh import db

    if key not in DEFAULTS:
        raise KeyError(f"Unknown setting: {key}")
    value = db.get_setting(key)
    if value is None:
        return DEFAULTS[key]
    try:
        normalize(key, value)
    except SettingError:  # a hand-edited or old value: fall back to the default instead of crashing
        return DEFAULTS[key]
    return value


def set_value(key: str, value: str) -> None:
    from adhyaksh import db

    db.set_setting(key, normalize(key, value))


def validate_all() -> list[dict]:
    """Stored settings that are invalid (they are ignored and the default is used). For the Health page."""
    from adhyaksh import db

    problems = []
    for key in DEFAULTS:
        value = db.get_setting(key)
        if value is None:
            continue
        try:
            normalize(key, value)
        except SettingError as exc:
            problems.append({"key": key, "value": value[:80], "problem": str(exc), "using": DEFAULTS[key]})
    return problems


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

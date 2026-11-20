"""Service layer for the Health page: the state of every dependency, model file, setting and service.

Each check returns {"area", "name", "state", "detail"} where state is one of:
  ok        working
  optional  an optional part that is not installed (the app works without it)
  missing   a required part is missing (the app may not work fully)
  problem   installed but not working, or a setting is invalid
Nothing here downloads anything or sends anything to the internet. API keys are reported only as present or absent.
"""
from __future__ import annotations

import importlib.metadata
import importlib.util
import platform
import shutil
import sys

from adhyaksh import __version__, config, db, logging_setup

# (distribution name, import name)
CORE = [("streamlit", "streamlit"), ("numpy", "numpy"), ("pandas", "pandas"), ("scikit-learn", "sklearn"),
        ("openpyxl", "openpyxl"), ("python-docx", "docx"), ("PyMuPDF", "fitz"), ("psutil", "psutil"), ("pycaw", "pycaw"), ("fastapi", "fastapi"), ("uvicorn", "uvicorn"),
        ("Send2Trash", "send2trash"), ("python-dotenv", "dotenv"), ("requests", "requests"),
        ("matplotlib", "matplotlib"), ("Pillow", "PIL")]
OPTIONAL = [("torch", "torch", "MLP intent model (M2)"),
            ("ultralytics", "ultralytics", "object detection"),
            ("onnxruntime", "onnxruntime", "local embeddings and OCR"),
            ("fastembed", "fastembed", "local multilingual document search"),
            ("faster-whisper", "faster_whisper", "local speech-to-text"),
            ("rapidocr-onnxruntime", "rapidocr_onnxruntime", "reading text in images (OCR)")]

version = __version__


def _row(area: str, name: str, state: str, detail: str = "") -> dict:
    return {"area": area, "name": name, "state": state, "detail": detail}


def _pkg_version(dist: str) -> str:
    try:
        return importlib.metadata.version(dist)
    except importlib.metadata.PackageNotFoundError:
        return ""


def _installed(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def package_checks() -> list[dict]:
    rows = [_row("Python", f"Python {platform.python_version()}",
                 "ok" if sys.version_info[:2] in ((3, 11), (3, 12)) else "problem",
                 "" if sys.version_info[:2] in ((3, 11), (3, 12)) else "Python 3.11 or 3.12 is recommended.")]
    for dist, mod in CORE:
        ok = _installed(mod)
        rows.append(_row("Required packages", dist, "ok" if ok else "missing",
                         _pkg_version(dist) if ok else "Run: pip install -r requirements-core.txt"))
    for dist, mod, use in OPTIONAL:
        ok = _installed(mod)
        rows.append(_row("Optional packages", dist, "ok" if ok else "optional",
                         f"{_pkg_version(dist)} - {use}" if ok else f"not installed - {use}"))
    return rows


def model_checks() -> list[dict]:
    from adhyaksh.nlu import registry
    from adhyaksh.rag import embedder
    from adhyaksh.vision import detector, ocr
    from adhyaksh.voice import stt

    rows = []
    try:
        active = registry.active_model_row() or {}
        usable = registry.available()
        rows.append(_row("Models", "Intent model", "ok" if usable else "missing",
                         active.get("name", "") if usable else "Train it: python -m adhyaksh.nlu.train --all"))
    except Exception as exc:  # a broken model file must not break the Health page
        rows.append(_row("Models", "Intent model", "problem", f"could not load ({type(exc).__name__})"))
    for choice, fname in detector.DETECTION_MODELS.items():
        present = detector._model_path(fname).exists()
        rows.append(_row("Models", f"Object detection ({choice}, {fname})", "ok" if present else "optional",
                         "" if present else "downloaded on first use from the Object Detection page"))
    rows.append(_row("Models", "Open-vocabulary detection (YOLO-World)",
                     "ok" if detector.world_available() else "optional",
                     "" if detector.world_available() else "needs the CLIP package and its weights; not installed by itself"))
    if stt.installed():
        rows.append(_row("Models", f"Speech model ({stt.model_size()})", "ok" if stt.model_present() else "optional",
                         "" if stt.model_present() else "download it from Settings, Voice"))
    if embedder.installed():
        rows.append(_row("Models", "Embedding model", "ok" if embedder.model_present() else "optional",
                         "" if embedder.model_present() else "download it from Settings, Document search"))
    ocr_engine = "rapidocr" if ocr.installed() else "tesseract" if ocr.tesseract_available() else ""
    rows.append(_row("Models", "Text reading (OCR)", "ok" if ocr_engine else "optional",
                     ocr_engine or "pip install rapidocr_onnxruntime"))
    return rows


def service_checks(probe_ollama: bool = True) -> list[dict]:
    from adhyaksh.llm import base as llm

    rows = []
    try:
        rows.append(_row("Storage", "Database", "ok", f"{config.db_path()} (schema v{db.schema_version()})"))
        check = (db.query_one("PRAGMA quick_check") or {})
        status = next(iter(check.values()), "ok") if check else "ok"
        if status != "ok":
            rows.append(_row("Storage", "Database integrity", "problem", str(status)))
    except Exception as exc:
        rows.append(_row("Storage", "Database", "problem", f"could not open ({type(exc).__name__})"))
    try:
        free_gb = shutil.disk_usage(config.data_dir()).free / 1e9
        rows.append(_row("Storage", "Free disk space", "ok" if free_gb >= 1 else "problem", f"{free_gb:.1f} GB"))
    except OSError:
        pass
    rows.append(_row("Storage", "Log file", "ok", str(logging_setup.log_path())))

    provider = config.get("llm_provider")
    consent = config.get_bool("cloud_consent")
    if not provider:
        rows.append(_row("Language model", "Provider", "optional", "none chosen; the app works offline with rules and local models"))
    elif llm.provider_is_local(provider):
        state, detail = "ok", "local, nothing leaves this computer"
        if provider == "openai_compat" and not config.get("openai_compat_model"):
            state, detail = "problem", "set the model name for the OpenAI-compatible server in Settings"
        elif probe_ollama and provider == "ollama":
            from adhyaksh import net
            try:
                net.get("http://127.0.0.1:11434/api/tags", timeout=1.5, attempts=1)
            except Exception:
                state, detail = "problem", "Ollama is not running. Start the Ollama program."
        rows.append(_row("Language model", f"Provider: {provider}", state, detail))
    else:
        has_key = bool(llm.api_key(provider)) and (provider != "openai_compat" or bool(config.get("openai_compat_model")))
        state = "ok" if has_key and consent else "problem"
        detail = ("key present, cloud use allowed" if state == "ok" else
                  "no API key" if not has_key else "cloud use is not allowed; turn it on in Settings to use this provider")
        rows.append(_row("Language model", f"Provider: {provider}", state, detail))
    rows.append(_row("Language model", "Cloud use", "ok", "allowed" if consent else "not allowed (private mode)"))

    problems = config.validate_all()
    if problems:
        for p in problems:
            rows.append(_row("Settings", p["key"], "problem", f"{p['problem']} Using the default: {p['using'] or '(empty)'}"))
    else:
        rows.append(_row("Settings", "All settings", "ok", "valid"))
    return rows


def checks(probe_ollama: bool = True) -> list[dict]:
    """Every check, in display order."""
    return package_checks() + model_checks() + service_checks(probe_ollama)


def summary(rows: list[dict]) -> dict:
    out = {"ok": 0, "optional": 0, "missing": 0, "problem": 0}
    for r in rows:
        out[r["state"]] = out.get(r["state"], 0) + 1
    return out


def recent_log(n: int = 30, min_level: str = "WARNING") -> list[dict]:
    return logging_setup.read_recent(n, min_level)

"""Structured logging: one JSON object per line in data/logs/adhyaksh.jsonl, with automatic redaction of
anything that looks like a secret.

    from adhyaksh import logging_setup as logs
    logs.event("tool_action", action="file_read", ok=True, ms=12)

Each line looks like {"ts": "...", "level": "INFO", "logger": "adhyaksh", "event": "tool_action", "action": ...}.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler

from adhyaksh import config

LOG_NAME = "adhyaksh.jsonl"
_SECRET = re.compile(
    r"(gsk_[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{16,}"
    r"|(?i:api[_-]?key)\s*[=:]\s*\S+)"
)


def redact(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)


def _clean(value):
    if isinstance(value, str):
        return redact(value)[:2000]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_clean(v) for v in value][:50]
    if isinstance(value, dict):
        return {str(k): _clean(v) for k, v in list(value.items())[:50]}
    return redact(str(value))[:2000]


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line. Extra fields come from `extra={"fields": {...}}`."""

    def format(self, record: logging.LogRecord) -> str:
        out = {"ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
               "level": record.levelname, "logger": record.name, "event": redact(record.getMessage())}
        for k, v in (getattr(record, "fields", None) or {}).items():
            if k not in out:
                out[k] = _clean(v)
        if record.exc_info:
            out["error"] = redact(self.formatException(record.exc_info))[-4000:]
        return json.dumps(out, ensure_ascii=False)


def log_path():
    return config.logs_dir() / LOG_NAME


def setup(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("adhyaksh")
    if getattr(logger, "_adhyaksh_ready", False):
        return logger
    logger.setLevel(level)
    handler = RotatingFileHandler(log_path(), maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactFilter())
    logger.addHandler(handler)
    logger.propagate = False
    logger._adhyaksh_ready = True  # type: ignore[attr-defined]
    return logger


def reset() -> None:
    """Close the log file handler so the next event opens the log in the current data folder (tests)."""
    logger = logging.getLogger("adhyaksh")
    for h in list(logger.handlers):
        logger.removeHandler(h)
        h.close()
    logger._adhyaksh_ready = False  # type: ignore[attr-defined]


def event(name: str, severity: int = logging.INFO, exc_info=None, **fields) -> None:
    """Write one structured log line. Never raises (logging must not break the app)."""
    try:
        setup().log(severity, name, extra={"fields": fields}, exc_info=exc_info)
    except Exception:
        pass


def read_recent(n: int = 50, min_level: str = "INFO") -> list[dict]:
    """The last n log lines at or above min_level, newest first (for the Health page)."""
    order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
    try:
        lines = log_path().read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines):
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if order.get(rec.get("level", "INFO"), 20) >= order.get(min_level, 20):
            out.append(rec)
        if len(out) >= n:
            break
    return out

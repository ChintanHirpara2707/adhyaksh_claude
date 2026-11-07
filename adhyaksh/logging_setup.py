"""Logging with automatic redaction of anything that looks like a secret."""
from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler

from adhyaksh import config

_SECRET = re.compile(
    r"(gsk_[A-Za-z0-9]{10,}|AIza[0-9A-Za-z_\-]{20,}|sk-[A-Za-z0-9]{16,}"
    r"|(?i:api[_-]?key)\s*[=:]\s*\S+)"
)


def redact(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


def setup(level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("adhyaksh")
    if getattr(logger, "_adhyaksh_ready", False):
        return logger
    logger.setLevel(level)
    handler = RotatingFileHandler(
        config.logs_dir() / "adhyaksh.log", maxBytes=512_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s"))
    handler.addFilter(RedactFilter())
    logger.addHandler(handler)
    logger.propagate = False
    logger._adhyaksh_ready = True  # type: ignore[attr-defined]
    return logger

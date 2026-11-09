"""Common Result object and error codes returned by every service function."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

E_PATH_DENIED = "E_PATH_DENIED"
E_NEEDS_CONFIRM = "E_NEEDS_CONFIRM"
E_NO_API_KEY = "E_NO_API_KEY"
E_TIMEOUT = "E_TIMEOUT"
E_FILE_NOT_FOUND = "E_FILE_NOT_FOUND"
E_LOW_CONFIDENCE = "E_LOW_CONFIDENCE"
E_UNSUPPORTED_OS = "E_UNSUPPORTED_OS"
E_BLOCKED = "E_BLOCKED"
E_ACTION_FAILED = "E_ACTION_FAILED"
E_CONFIRM_INVALID = "E_CONFIRM_INVALID"


@dataclass(frozen=True)
class Result:
    """Outcome of a service call. Expected failures never raise to the UI."""

    ok: bool
    data: Any = None
    error_code: str = ""
    message: str = ""

    @classmethod
    def success(cls, data: Any = None, message: str = "") -> "Result":
        return cls(True, data, "", message)

    @classmethod
    def failure(cls, error_code: str, message: str = "", data: Any = None) -> "Result":
        return cls(False, data, error_code, message)

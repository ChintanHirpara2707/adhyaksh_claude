"""Authorization: permission levels L0-L3, allowed-folder enforcement, guarded execution.

Levels: L0 read-only, L1 reversible, L2 destructive (needs confirmation), L3 blocked.
Audit rule: every action attempt ends in exactly one audit row (executed, failed, blocked,
rejected or cancelled). Creating a pending confirmation is not yet an action and writes no row.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from adhyaksh import config
from adhyaksh.result import (
    E_ACTION_FAILED, E_BLOCKED, E_CONFIRM_INVALID, E_NEEDS_CONFIRM, E_PATH_DENIED, Result,
)
from adhyaksh.safety import audit
from adhyaksh.safety.confirm import STORE, ConfirmationStore

LEVELS: dict[str, int] = {
    "file_list": 0, "file_read": 0, "file_search": 0, "memory_read": 0,
    "doc_query": 0, "system_status": 0,
    "file_create": 1, "file_append": 1, "office_create": 1, "app_open": 1, "memory_write": 1,
    "screenshot": 1, "web_open": 1, "special_folder_open": 1,
    "file_overwrite": 2, "file_delete": 2, "app_close": 2, "memory_delete": 2,
    "run_python": 2,
    "shell_exec": 3,
}
PATH_ACTIONS = {
    "file_list", "file_read", "file_search", "file_create", "file_append",
    "file_overwrite", "file_delete", "office_create",
}
MODIFYING_PATH_ACTIONS = {"file_overwrite", "file_delete"}


@dataclass(frozen=True)
class Decision:
    level: int
    allowed: bool
    needs_confirmation: bool
    reason: str


def _norm(p: Path | str) -> str:
    return os.path.normcase(str(p))


def is_within(child: Path, parent: Path) -> bool:
    try:
        return os.path.commonpath([_norm(child), _norm(parent)]) == _norm(parent)
    except ValueError:  # different drives
        return False


def system_dirs() -> list[Path]:
    dirs: list[str] = []
    if os.name == "nt":
        for var, fallback in (("SystemRoot", r"C:\Windows"), ("ProgramFiles", r"C:\Program Files"),
                              ("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                              ("ProgramData", r"C:\ProgramData")):
            dirs.append(os.environ.get(var, fallback))
    else:
        dirs = ["/etc", "/usr", "/bin", "/sbin", "/boot", "/sys", "/proc", "/dev",
                "/lib", "/lib64", "/var", "/root", "/System", "/Library"]
    return [Path(d) for d in dirs]


def is_system_path(p: Path) -> bool:
    if p == Path(p.anchor) or _norm(p) == _norm(Path.home().resolve()):
        return True  # drive or filesystem root, or the user profile root itself
    return any(is_within(p, d) for d in system_dirs())


def check_path(target: str, roots: Iterable[Path], base: Path | None = None) -> tuple[Path | None, str]:
    """Resolve target and verify it lies inside an allowed root. Returns (path, reason)."""
    if not target or "\x00" in target:
        return None, "No valid path was supplied."
    valid_roots = [r for r in roots if not is_system_path(r)]
    if not valid_roots:
        return None, "No allowed folders are configured."
    p = Path(target).expanduser()
    if not p.is_absolute():
        p = (base or valid_roots[0]) / p
    resolved = p.resolve(strict=False)
    if is_system_path(resolved):
        return None, "System folders are never accessible."
    if not any(is_within(resolved, r) for r in valid_roots):
        return None, "The path is outside the allowed folders."
    return resolved, ""


def authorize(action: str, target: str = "", allowed_roots: Iterable[Path] | None = None,
              base: Path | None = None) -> Decision:
    """Assign a level to an action and enforce folder rules. Pure: no side effects."""
    level = LEVELS.get(action)
    if level is None:
        return Decision(3, False, False, f"Unknown action type: {action}.")
    if level == 3:
        return Decision(3, False, False, "This action type is never permitted.")
    if action in PATH_ACTIONS:
        roots = list(allowed_roots) if allowed_roots is not None else config.get_allowed_roots()
        resolved, reason = check_path(target, roots, base)
        if resolved is None:
            return Decision(3, False, False, reason)
        if action in MODIFYING_PATH_ACTIONS and any(_norm(resolved) == _norm(r) for r in roots):
            return Decision(3, False, False, "An allowed root folder cannot be modified or deleted.")
    if level == 2:
        return Decision(2, True, True, "Confirmation required.")
    return Decision(level, True, False, "Allowed.")


def run_guarded(
    action: str, target: str, runner: Callable[[], Result], *,
    user_text: str = "", intent: str = "", token: str | None = None,
    allowed_roots: Iterable[Path] | None = None, base: Path | None = None,
    store: ConfirmationStore = STORE,
) -> Result:
    """The single gateway for tool actions. Nothing else may call a tool runner."""
    d = authorize(action, target, allowed_roots, base)

    def log(result: str, confirmed: str = "none") -> None:
        audit.record(user_text=user_text, intent=intent, action=action, target=target,
                     level=d.level, confirmed=confirmed, result=result)

    if not d.allowed:
        log(f"blocked: {d.reason}")
        code = E_PATH_DENIED if action in PATH_ACTIONS else E_BLOCKED
        return Result.failure(code, d.reason)

    confirmed = "none"
    if d.needs_confirmation:
        if token is None:
            pending = store.create(action, target, user_text, intent)
            return Result.failure(E_NEEDS_CONFIRM, d.reason, {"token": pending.token,
                                                              "action": action, "target": target})
        if store.consume(token, action, target) is None:
            log("rejected: invalid or expired confirmation")
            return Result.failure(E_CONFIRM_INVALID, "The confirmation is invalid or has expired.")
        confirmed = "confirmed"

    try:
        res = runner()
    except Exception as exc:  # expected tool failures must not reach the UI as exceptions
        log(f"error: {type(exc).__name__}", confirmed)
        return Result.failure(E_ACTION_FAILED, "The action raised an unexpected error.")
    log("ok" if res.ok else f"failed: {res.error_code}", confirmed)
    return res


def cancel_guarded(token: str, *, store: ConfirmationStore = STORE) -> Result:
    """User pressed Cancel on a confirmation card. Writes one audit row."""
    pending = store.cancel(token)
    if pending is None:
        return Result.failure(E_CONFIRM_INVALID, "The confirmation is invalid or has expired.")
    audit.record(user_text=pending.user_text, intent=pending.intent, action=pending.action,
                 target=pending.target, level=2, confirmed="cancelled", result="cancelled by user")
    return Result.success(message="Action cancelled.")


def deny(action: str, target: str, reason: str, *, user_text: str = "", intent: str = "",
         code: str = E_BLOCKED) -> Result:
    """Refuse an action before it starts (for example an application outside the allow-list).
    Writes exactly one audit row at level 3."""
    audit.record(user_text=user_text, intent=intent, action=action, target=target, level=3,
                 confirmed="none", result=f"blocked: {reason}")
    return Result.failure(code, reason)

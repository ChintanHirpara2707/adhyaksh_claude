"""Post-condition checks and failure diagnosis, applied by the safety gateway to every tool action.

* :func:`check`: after a tool reports success, look at the computer and confirm the effect is really there (the
  file exists, the deleted file is gone, the app process is alive or gone, the reminder row is pending, the
  clipboard holds the text). A failed check turns the result into ``E_UNVERIFIED``; a check that cannot tell
  leaves the result as it is and records ``verified: None``.
* :func:`explain`: every failure gets ``retryable`` (would the same action with corrected arguments, or a second
  try, reasonably succeed?) and a ``hint`` (for example the names of similar files). Actions at level 2 and above
  are never marked retryable: a destructive action is not repeated automatically.

Because the gateway is the one path every action takes (rules, multi-step requests and the agent), verification
and diagnosis are written once and apply everywhere.
"""
from __future__ import annotations

import difflib
from pathlib import Path
from typing import Callable

from adhyaksh.result import (E_ACTION_FAILED, E_BAD_ARGUMENTS, E_BLOCKED, E_CONFIRM_INVALID, E_FILE_NOT_FOUND, E_NETWORK,
                             E_PATH_DENIED, E_TIMEOUT, E_UNVERIFIED, Result)

_CHECKS: dict[str, Callable[[str, dict], tuple[bool | None, str]]] = {}


def verifier(*actions: str):
    def deco(fn):
        for a in actions:
            _CHECKS[a] = fn
        return fn
    return deco


@verifier("file_create", "office_create", "file_append", "file_overwrite")
def _path_exists(target: str, data: dict):
    p = data.get("path")
    if not p:
        return None, ""
    return (True, "") if Path(p).exists() else (False, f"{Path(p).name} does not exist after the action")


@verifier("file_delete")
def _path_gone(target: str, data: dict):
    p = data.get("path")
    if not p:
        return None, ""
    return (True, "") if not Path(p).exists() else (False, f"{Path(p).name} is still there after the action")


@verifier("app_open")
def _app_running(target: str, data: dict):
    pid = data.get("pid")
    if not pid:
        return None, ""  # opened through the Windows shell: there is no process id to check
    import psutil
    try:
        alive = psutil.pid_exists(int(pid)) and psutil.Process(int(pid)).status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        alive = False
    if alive:
        return True, ""
    from adhyaksh.tools import apps
    # The launcher may hand over to another process (calc.exe starts CalculatorApp.exe and exits).
    app = data.get("app") or target
    if apps._find_processes(app, apps.allowlist().get(app, [])):
        return True, ""
    return False, f"{app} is not running after it was started"


@verifier("app_close")
def _app_gone(target: str, data: dict):
    if "closed" not in data:
        return None, ""
    from adhyaksh.tools import apps
    app = data.get("app") or target
    remaining = len(apps._find_processes(app, apps.allowlist().get(app, []))) - int(data.get("waiting") or 0)
    return (True, "") if remaining <= 0 else (False, f"{app} is still running ({remaining} process(es))")


@verifier("process_kill")
def _process_gone(target: str, data: dict):
    """The exact processes that were ended are gone (other processes with the same name are not the target)."""
    pids = data.get("pids")
    if not pids:
        return None, ""
    import psutil
    left = []
    for pid in pids:
        try:
            p = psutil.Process(int(pid))
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                left.append(pid)
        except psutil.Error:
            continue
    return (True, "") if not left else (False, f"{data.get('name', target)} is still running ({len(left)} process(es))")


@verifier("reminder_add")
def _reminder_saved(target: str, data: dict):
    rid = data.get("id")
    if not rid:
        return None, ""
    from adhyaksh import db
    row = db.query_one("SELECT status FROM reminders WHERE id=?", (rid,))
    return (True, "") if row and row["status"] == "pending" else (False, "the reminder was not saved")


@verifier("clipboard_write")
def _clipboard_holds(target: str, data: dict):
    if "text" not in data:
        return None, ""
    try:
        from adhyaksh.tools import clipboard
        now = clipboard.get_text()
    except Exception:  # the clipboard may be busy: that is "cannot tell", not a failure
        return None, ""
    return (True, "") if now == data["text"] else (False, "the clipboard does not hold the new text")


@verifier("volume_control")
def _volume_reads_back(target: str, data: dict):
    from adhyaksh.tools import audio
    now = audio.read(data.get("device", "speaker"))
    if not now.ok:
        return None, ""
    if data.get("op") in ("mute", "unmute"):
        ok = now.data["muted"] == (data["op"] == "mute")
        return (True, "") if ok else (False, f"the {data.get('device')} is not {'muted' if data['op'] == 'mute' else 'unmuted'}")
    ok = abs(now.data["level"] - int(data.get("level", -100))) <= 2
    return (True, "") if ok else (False, f"the {data.get('device')} is at {now.data['level']} percent, not {data.get('level')}")


@verifier("brightness_control")
def _brightness_reads_back(target: str, data: dict):
    from adhyaksh.tools import display
    now = display.read()
    if not now.ok or "level" not in data:
        return None, ""
    # Many laptops only have brightness steps (0, 5, 10 ...): a small difference is still the requested level.
    ok = abs(now.data["level"] - int(data["level"])) <= 10
    return (True, "") if ok else (False, f"the brightness is {now.data['level']} percent, not {data['level']}")


def check(action: str, target: str, res: Result) -> Result:
    """The result, with data['verified'] set, or an E_UNVERIFIED failure when the effect is not there."""
    fn = _CHECKS.get(action)
    if fn is None or not res.ok or not isinstance(res.data, dict):
        return res
    try:
        ok, detail = fn(target, res.data)
    except Exception:  # a check must never break the action it checks
        ok, detail = None, ""
    if ok is False:
        return Result.failure(E_UNVERIFIED, f"The action reported success, but {detail}.",
                              data={**res.data, "verified": False, "retryable": True,
                                    "hint": "check the name or target and try once more"})
    return Result(True, {**res.data, "verified": ok}, "", res.message)


_NEVER_RETRY = {E_BLOCKED, E_PATH_DENIED, E_CONFIRM_INVALID}
_RETRY = {E_TIMEOUT, E_NETWORK, E_BAD_ARGUMENTS, E_UNVERIFIED}


def similar_files(target: str, base: Path | None = None, n: int = 3) -> list[str]:
    """Names in the folder of the missing file (or the work folder) that look like it."""
    from adhyaksh import config
    name = Path(target).name
    folder = Path(target).parent if Path(target).is_absolute() else Path(base or config.get("default_work_folder"))
    try:
        names = [p.name for p in folder.iterdir()][:2000]
    except OSError:
        return []
    return difflib.get_close_matches(name, names, n=n, cutoff=0.6)


def explain(action: str, target: str, level: int, res: Result, base: Path | None = None) -> Result:
    """A failure with 'retryable' and 'hint' in its data. Success and confirmation requests pass unchanged."""
    from adhyaksh.result import E_NEEDS_CONFIRM
    if res.ok or res.error_code == E_NEEDS_CONFIRM:
        return res
    data = dict(res.data) if isinstance(res.data, dict) else {}
    hint = data.get("hint", "")
    if res.error_code == E_FILE_NOT_FOUND or "not found" in (res.message or "").casefold():
        near = similar_files(target, base) if target else []
        hint = f"similar names: {', '.join(near)}" if near else hint or "no similar name in that folder"
        retryable = bool(near)
    elif res.error_code in _NEVER_RETRY:
        retryable = False
    elif res.error_code in _RETRY:
        retryable = True
    elif res.error_code == E_ACTION_FAILED and "not running" in (res.message or ""):
        retryable, hint = False, hint or "it is already closed"
    else:
        retryable = bool(data.get("retryable", False))
    if level >= 2:
        retryable = False  # destructive actions are never repeated automatically
    data.update(retryable=retryable, hint=hint)
    return Result(False, data, res.error_code, res.message)

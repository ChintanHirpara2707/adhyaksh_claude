"""Battery, power plan, lock, sleep, restart and shut down.

* battery() and power_plan() only read (psutil, powercfg).
* lock() is level 1: unlocking needs the user's own PIN or password, so nothing is lost.
* sleep, restart and shut down are level 2 (unsaved work could be lost): the user confirms. Restart and shut down
  are scheduled with a 60-second delay through Windows' own `shutdown` command, so "cancel the shutdown" (level 1)
  can still stop them; sleep happens at once after the confirmation.
Commands are fixed argument lists (no shell, no user text).
"""
from __future__ import annotations

import os
import subprocess

from adhyaksh.result import E_ACTION_FAILED, E_BAD_ARGUMENTS, E_UNSUPPORTED_OS, Result
from adhyaksh.safety import policy

DELAY_SECONDS = 60
OPS = ("lock", "sleep", "restart", "shutdown", "cancel")
_COMMANDS = {
    "shutdown": ["shutdown", "/s", "/t", str(DELAY_SECONDS)],
    "restart": ["shutdown", "/r", "/t", str(DELAY_SECONDS)],
    "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    "cancel": ["shutdown", "/a"],
}
_ACTIONS = {"lock": "screen_lock", "sleep": "power_off", "restart": "power_off", "shutdown": "power_off",
            "cancel": "power_cancel"}


def _ctx(ctx: dict | None) -> dict:
    ctx = ctx or {}
    return {"user_text": ctx.get("user_text", ""), "intent": ctx.get("intent", "")}


def battery() -> Result:
    import psutil
    b = psutil.sensors_battery()
    if b is None:
        return Result.success({"present": False})
    left = None if b.secsleft in (psutil.POWER_TIME_UNLIMITED, psutil.POWER_TIME_UNKNOWN) or b.secsleft < 0 else int(b.secsleft // 60)
    return Result.success({"present": True, "percent": round(b.percent), "plugged": bool(b.power_plugged), "minutes_left": left})


def power_plan() -> str:
    """The active power plan's name ('Balanced'), or '' when it cannot be read."""
    if os.name != "nt":
        return ""
    try:
        out = subprocess.run(["powercfg", "/getactivescheme"], capture_output=True, text=True, timeout=10,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return out.rsplit("(", 1)[-1].rstrip(") \r\n") if "(" in out else ""


def _run(cmd: list[str]) -> bool:
    try:
        return subprocess.run(cmd, capture_output=True, timeout=15,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _lock() -> bool:
    import ctypes
    return bool(ctypes.windll.user32.LockWorkStation())  # type: ignore[attr-defined]


def act(op: str, *, ctx: dict | None = None) -> Result:
    """lock, sleep, restart, shutdown, or cancel a scheduled restart or shutdown."""
    if op not in OPS:
        return Result.failure(E_BAD_ARGUMENTS, f"op must be one of: {', '.join(OPS)}.")
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Power actions work on Windows only.")
    target = {"lock": "lock the PC", "sleep": "put the PC to sleep", "restart": f"restart the PC in {DELAY_SECONDS} seconds",
              "shutdown": f"shut down the PC in {DELAY_SECONDS} seconds", "cancel": "cancel the scheduled shutdown"}[op]

    def go() -> Result:
        ok = _lock() if op == "lock" else _run(_COMMANDS[op])
        if not ok:
            if op == "cancel":
                return Result.failure(E_ACTION_FAILED, "There is no scheduled shutdown or restart to cancel.")
            return Result.failure(E_ACTION_FAILED, f"Windows did not {target}.")
        return Result.success({"op": op, "delay_seconds": DELAY_SECONDS if op in ("restart", "shutdown") else 0})

    return policy.run_guarded(_ACTIONS[op], target, go, token=(ctx or {}).get("token"), **_ctx(ctx))

"""Display brightness of a laptop's built-in screen (Windows WMI, run through PowerShell with a fixed script and a
validated whole number; no shell, no user text in the command). External monitors usually do not support it, and
the result says so plainly. Changes go through the safety gateway (level 1) and are read back.
"""
from __future__ import annotations

import os
import subprocess

from adhyaksh.result import E_ACTION_FAILED, E_BAD_ARGUMENTS, E_UNSUPPORTED_OS, Result
from adhyaksh.safety import policy

STEP = 10
OPS = ("set", "up", "down")
_READ = "(Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightness -ErrorAction Stop | Select-Object -First 1).CurrentBrightness"
_WRITE = ("$m = Get-CimInstance -Namespace root/WMI -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop | Select-Object -First 1; "
          "Invoke-CimMethod -InputObject $m -MethodName WmiSetBrightness -Arguments @{{Timeout=1; Brightness=[byte]{level}}} | Out-Null; 'ok'")


def powershell(script: str, timeout: float = 15.0) -> tuple[bool, str]:
    """Run a fixed PowerShell script without a window. Returns (ok, stdout or error)."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script],
                             capture_output=True, text=True, timeout=timeout, creationflags=flags)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, type(exc).__name__
    return out.returncode == 0, (out.stdout or out.stderr or "").strip()


def as_level(level) -> int | None | bool:
    """A whole number 0-100, None when not given, or False when it is anything else (text, out of range, a bool)."""
    if level is None:
        return None
    if isinstance(level, bool):
        return False
    if isinstance(level, str):
        if not level.strip().isdigit():
            return False
        level = int(level.strip())
    if not isinstance(level, int) or not 0 <= level <= 100:
        return False
    return level


def _ctx(ctx: dict | None) -> dict:
    ctx = ctx or {}
    return {"user_text": ctx.get("user_text", ""), "intent": ctx.get("intent", "")}


def read() -> Result:
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Brightness control works on Windows only.")
    ok, out = powershell(_READ)
    if not ok or not out.strip().isdigit():
        return Result.failure(E_ACTION_FAILED, "This screen does not report its brightness (an external monitor usually cannot "
                                               "be dimmed from Windows).")
    return Result.success({"level": int(out.strip())})


def control(op: str, level: int | None = None, *, ctx: dict | None = None) -> Result:
    if op not in OPS:
        return Result.failure(E_BAD_ARGUMENTS, f"op must be one of: {', '.join(OPS)}.")
    if op == "set" and level is None:
        return Result.failure(E_BAD_ARGUMENTS, "Say the brightness to set, for example 70 percent.")
    level = as_level(level)
    if level is False:
        return Result.failure(E_BAD_ARGUMENTS, "The brightness must be a whole number between 0 and 100.")
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Brightness control works on Windows only.")
    target = f"brightness {op}" + (f" {level}" if level is not None else "")

    def go() -> Result:
        now = read()
        if not now.ok:
            return now
        current = now.data["level"]
        new = {"set": int(level or 0), "up": current + int(level or STEP), "down": current - int(level or STEP)}[op]
        new = max(0, min(100, new))
        ok, out = powershell(_WRITE.format(level=int(new)))
        if not ok:
            return Result.failure(E_ACTION_FAILED, "Windows did not accept the brightness change for this screen.")
        return Result.success({"op": op, "level": new, "previous": current})

    return policy.run_guarded("brightness_control", target, go, **_ctx(ctx))

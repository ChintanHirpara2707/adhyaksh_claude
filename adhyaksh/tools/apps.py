"""Application launcher restricted to an allow-list. No shell, no arbitrary commands."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED, E_BLOCKED, Result
from adhyaksh.safety import policy

ALIASES = {"नोटपैड": "notepad", "कैलकुलेटर": "calculator", "क्रोम": "chrome", "पेंट": "paint",
           "નોટપેડ": "notepad", "કેલ્ક્યુલેટર": "calculator", "ક્રોમ": "chrome", "પેઇન્ટ": "paint",
           "vscode": "vs code", "code": "vs code", "google chrome": "chrome", "calc": "calculator"}
_LAUNCHED: dict[str, list[int]] = {}


def allowlist() -> dict[str, list[str]]:
    """Saved allow-list merged with new default apps (saved entries win)."""
    try:
        raw = json.loads(config.get("app_allowlist"))
    except json.JSONDecodeError:
        raw = {}
    saved = {
        str(k).casefold(): [str(x) for x in v]
        for k, v in raw.items() if isinstance(v, list) and v
    }
    defaults = config.default_app_allowlist()
    merged = dict(saved)
    for key, cmd in defaults.items():
        if key not in merged:
            merged[key] = cmd
    return merged


def set_allowlist(text: str) -> Result:
    """Validate JSON of the form {"name": ["command", "arg"]} and save it."""
    try:
        data = json.loads(text)
        ok = isinstance(data, dict) and all(isinstance(k, str) and isinstance(v, list) and v
                                            and all(isinstance(x, str) for x in v) for k, v in data.items())
    except json.JSONDecodeError:
        ok = False
    if not ok:
        return Result.failure(E_ACTION_FAILED, 'Use JSON like {"notepad": ["notepad.exe"]}.')
    config.set_value("app_allowlist", json.dumps(data))
    return Result.success()


def resolve_name(name: str) -> str:
    key = (name or "").strip().casefold()
    return ALIASES.get(key, key)


def open_app(name: str, *, ctx: dict | None = None) -> Result:
    ctx = ctx or {}
    key, apps = resolve_name(name), allowlist()
    if key not in apps:
        return policy.deny("app_open", name, f"{name} is not on the allowed applications list.",
                           user_text=ctx.get("user_text", ""), intent=ctx.get("intent", ""))

    def go() -> Result:
        cmd = apps[key]
        try:
            if os.name == "nt" and len(cmd) == 1 and not os.path.sep in cmd[0]:
                os.startfile(cmd[0])  # type: ignore[attr-defined]
                return Result.success({"app": key})
            proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            _LAUNCHED.setdefault(key, []).append(proc.pid)
            return Result.success({"app": key, "pid": proc.pid})
        except (OSError, AttributeError):
            # Fallback for WhatsApp: try the whatsapp: URI scheme, then give a clear reason.
            if key == "whatsapp":
                try:
                    os.startfile("whatsapp:")  # type: ignore[attr-defined]
                    return Result.success({"app": key})
                except (OSError, AttributeError):
                    pass
            return Result.failure(E_ACTION_FAILED, "The application was not found on this computer.")

    return policy.run_guarded("app_open", key, go, user_text=ctx.get("user_text", ""), intent=ctx.get("intent", ""))


def close_app(name: str, *, ctx: dict | None = None) -> Result:
    """L2: needs confirmation. Closes processes this program launched, or matching executables."""
    ctx = ctx or {}
    key, apps = resolve_name(name), allowlist()
    if key not in apps:
        return policy.deny("app_close", name, f"{name} is not on the allowed applications list.",
                           user_text=ctx.get("user_text", ""), intent=ctx.get("intent", ""))

    def go() -> Result:
        import psutil
        pids = set(_LAUNCHED.pop(key, []))
        exe = Path(apps[key][0]).name.casefold()
        for proc in psutil.process_iter(["pid", "name"]):
            if os.name == "nt" and (proc.info["name"] or "").casefold() == exe:
                pids.add(proc.info["pid"])
        closed = 0
        for pid in pids:
            try:
                psutil.Process(pid).terminate()
                closed += 1
            except psutil.Error:
                continue
        if not closed:
            return Result.failure(E_ACTION_FAILED, "No running instance was found.")
        return Result.success({"app": key, "closed": closed})

    return policy.run_guarded("app_close", key, go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""), token=ctx.get("token"))

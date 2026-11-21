"""Application launcher restricted to an allow-list. No shell, no arbitrary commands."""
from __future__ import annotations

import json
import os
import re
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


_STORE_ID = re.compile(r"^[A-Za-z0-9.\-]+_[a-z0-9]{13}![A-Za-z0-9.\-]+$")  # Publisher.App_hash!Entry
_START_APPS: dict[str, str] | None = None


def _start_apps() -> dict[str, str]:
    """Start menu apps that come from the Microsoft Store: {name casefold: app id}. Read once with a fixed
    PowerShell command (no user text in it); empty when that fails."""
    global _START_APPS
    if _START_APPS is None:
        _START_APPS = {}
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                                  "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"],
                                 capture_output=True, text=True, timeout=20,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            rows = json.loads(out.stdout or "[]")
            for r in rows if isinstance(rows, list) else [rows]:
                name, app_id = str(r.get("Name") or "").strip(), str(r.get("AppID") or "").strip()
                if name and _STORE_ID.match(app_id):
                    _START_APPS.setdefault(name.casefold(), app_id)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass
    return _START_APPS


def store_app_id(key: str) -> str | None:
    """The Store app id of an allow-listed app whose Start menu name is the key (WhatsApp, Spotify, ...)."""
    if os.name != "nt":
        return None
    apps = _start_apps()
    return apps.get(key.casefold()) or apps.get(key.replace(" ", "").casefold())


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
            # Microsoft Store apps (WhatsApp, Spotify from the Store, ...) have no exe on the path: start them by
            # their Start menu id, then try the whatsapp: link, then give a clear reason.
            app_id = store_app_id(key)
            for target in ([f"shell:AppsFolder\\{app_id}"] if app_id else []) + (["whatsapp:"] if key == "whatsapp" else []):
                try:
                    os.startfile(target)  # type: ignore[attr-defined]
                    return Result.success({"app": key, "store_app": bool(app_id)})
                except (OSError, AttributeError):
                    continue
            return Result.failure(E_ACTION_FAILED, "The application was not found on this computer.")

    return policy.run_guarded("app_open", key, go, user_text=ctx.get("user_text", ""), intent=ctx.get("intent", ""))


# The launch command often differs from the running process: "calc.exe" starts CalculatorApp.exe,
# "code" runs as Code.exe, the new WhatsApp runs as WhatsApp.Root.exe.
PROCESS_NAMES: dict[str, set[str]] = {
    "notepad": {"notepad.exe"},
    "calculator": {"calculatorapp.exe", "calculator.exe", "calc.exe", "win32calc.exe"},
    "paint": {"mspaint.exe", "paintapp.exe"},
    "snipping tool": {"snippingtool.exe", "screenclippinghost.exe"},
    "chrome": {"chrome.exe"}, "edge": {"msedge.exe"}, "brave": {"brave.exe"},
    "vs code": {"code.exe"}, "whatsapp": {"whatsapp.exe", "whatsapp.root.exe"},
    "spotify": {"spotify.exe"},
}
_EXPLORER_WINDOW = "CabinetWClass"  # File Explorer windows; explorer.exe itself is the taskbar and is never ended
_GRACE_SECONDS = 3.0
_SHARED_HOSTS = {"python", "pythonw", "py", "node", "java", "javaw", "powershell", "pwsh", "cmd",
                 "wscript", "cscript", "rundll32", "explorer", "start", "open", "sh", "bash"}


def process_names(key: str, cmd: list[str]) -> set[str]:
    """Process names that belong to an allow-listed app."""
    names = set(PROCESS_NAMES.get(key, set()))
    exe = Path(cmd[0]).name.casefold() if cmd else ""
    if Path(exe).stem in _SHARED_HOSTS:
        return names  # an interpreter runs many unrelated programs: only close what we launched
    if exe:
        names.add(exe)
        if os.name == "nt" and not Path(exe).suffix:
            names.add(exe + ".exe")
    if os.name == "nt" and key.replace(" ", "") not in _SHARED_HOSTS:
        names.add(key.replace(" ", "") + ".exe")
    return names


def _protected_pids() -> set[int]:
    """This program and the processes that started it (never ended, even if they share an exe name)."""
    import psutil
    pids = {os.getpid()}
    try:
        pids.update(p.pid for p in psutil.Process().parents())
    except psutil.Error:
        pass
    return pids


def _find_processes(key: str, cmd: list[str]) -> list:
    import psutil
    names, skip = process_names(key, cmd), _protected_pids()
    found: dict[int, psutil.Process] = {}
    for pid in _LAUNCHED.get(key, []):
        try:
            p = psutil.Process(pid)
            if p.is_running() and p.status() != psutil.STATUS_ZOMBIE:
                found[pid] = p
        except psutil.Error:
            continue
    for p in psutil.process_iter(["pid", "name"]):
        if (p.info["name"] or "").casefold() in names:
            found[p.info["pid"]] = p
    return [p for pid, p in found.items() if pid not in skip and _alive(p)]


def _alive(p) -> bool:
    """A process that is still running (a process that is exiting can still be listed for a moment)."""
    import psutil
    try:
        return p.is_running() and p.status() != psutil.STATUS_ZOMBIE
    except psutil.Error:
        return False


def _windows(pids: set[int] | None = None, class_name: str | None = None) -> list[tuple[int, int]]:
    """Visible top-level windows as (hwnd, pid), filtered by owner pid or window class. Windows only."""
    if os.name != "nt":
        return []
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32  # type: ignore[attr-defined]
    out: list[tuple[int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if class_name is not None:
                buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, buf, 256)
                if buf.value == class_name:
                    out.append((hwnd, pid.value))
            elif pids and pid.value in pids:
                out.append((hwnd, pid.value))
        return True

    user32.EnumWindows(cb, 0)
    return out


def _post_close(hwnds: list[int]) -> None:
    import ctypes
    for hwnd in hwnds:
        ctypes.windll.user32.PostMessageW(hwnd, 0x0010, 0, 0)  # type: ignore[attr-defined]  # WM_CLOSE


def _close_explorer_windows() -> Result:
    wins = _windows(class_name=_EXPLORER_WINDOW)
    if not wins:
        return Result.failure(E_ACTION_FAILED, "No File Explorer window is open.")
    _post_close([h for h, _ in wins])
    return Result.success({"app": "file explorer", "closed": len(wins), "waiting": 0})


def _close_processes(key: str, cmd: list[str]) -> Result:
    """Ask windows to close (like clicking X), then end what is left. An app that is still
    showing a window after the grace period is asking to save, so it is left for the user."""
    import psutil
    procs = _find_processes(key, cmd)
    if not procs:
        _LAUNCHED.pop(key, None)
        return Result.failure(E_ACTION_FAILED, f"{key} is not running.")
    with_window = {pid for _, pid in _windows({p.pid for p in procs})}
    if with_window:
        _post_close([h for h, _ in _windows(with_window)])
        psutil.wait_procs([p for p in procs if p.pid in with_window], timeout=_GRACE_SECONDS)
    waiting = 0
    alive = []
    for p in procs:
        try:
            if not p.is_running() or p.status() == psutil.STATUS_ZOMBIE:
                continue
        except psutil.Error:
            continue
        if p.pid in with_window and _windows({p.pid}):
            waiting += 1  # e.g. "Do you want to save changes?"
            continue
        alive.append(p)
    for p in alive:
        try:
            p.terminate()
        except psutil.Error:
            pass
    _, still = psutil.wait_procs(alive, timeout=_GRACE_SECONDS)
    for p in still:
        try:
            p.kill()
        except psutil.Error:
            pass
    _LAUNCHED.pop(key, None)
    return Result.success({"app": key, "closed": len(procs) - waiting, "waiting": waiting})


def close_app(name: str, *, ctx: dict | None = None) -> Result:
    """L1: closes an allow-listed app without asking. Windows are closed politely first, so an
    app with unsaved work shows its own save prompt instead of losing the work."""
    ctx = ctx or {}
    key, apps = resolve_name(name), allowlist()
    if key not in apps:
        if os.name == "nt":
            from adhyaksh.tools import windows
            if windows.find_tab(name) is not None:  # "close gmail": a site open in a browser tab, not an app
                return windows.close_tab(name, ctx=ctx)
        return policy.deny("app_close", name, f"{name} is not on the allowed applications list.",
                           user_text=ctx.get("user_text", ""), intent=ctx.get("intent", ""))

    def go() -> Result:
        if key == "file explorer" and os.name == "nt":
            return _close_explorer_windows()
        return _close_processes(key, apps[key])

    return policy.run_guarded("app_close", key, go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""), token=ctx.get("token"))

"""Window management: list the open windows; focus, minimise, maximise, restore or politely close one; minimise or
restore all. Windows are picked by app name (any spelling the app finder knows) or by words of their title, never
"this window" (while the user types, the active window is the assistant itself). ctypes + user32, no package.
Level 1 (nothing is lost: a close is a polite WM_CLOSE, so an app with unsaved work shows its own save prompt).
"""
from __future__ import annotations

import os
import time

from adhyaksh.result import E_ACTION_FAILED, E_BAD_ARGUMENTS, E_FILE_NOT_FOUND, E_UNSUPPORTED_OS, Result
from adhyaksh.safety import policy

OPS = ("focus", "minimize", "maximize", "restore", "close", "minimize_all", "restore_all")
_SW = {"minimize": 6, "maximize": 3, "restore": 9}
_ALL = {"minimize_all": "MinimizeAll", "restore_all": "UndoMinimizeALL"}


def _ctx(ctx: dict | None) -> dict:
    ctx = ctx or {}
    return {"user_text": ctx.get("user_text", ""), "intent": ctx.get("intent", "")}


def _user32():
    import ctypes
    return ctypes.windll.user32  # type: ignore[attr-defined]


_DWMWA_CLOAKED = 14
_GWL_EXSTYLE = -20
_WS_EX_TOOLWINDOW = 0x00000080
# Shell surfaces that are not app windows a user would count or switch to.
_SHELL_TITLES = {"Program Manager", "Windows Input Experience", "Microsoft Text Input Application", "Windows Shell Experience Host",
                 "Search", "Start", "Cortana", "Task View", "Action center", "Notification Center", "NVIDIA GeForce Overlay"}


def _raw_windows() -> list[dict]:
    """Every visible top-level window with a title, top of the stack first, with what is needed to judge it:
    cloaked (hidden by the window manager although 'visible': suspended Store apps, Settings, Cortana) and tool
    (a palette or helper window, not in Alt+Tab)."""
    import ctypes
    from ctypes import wintypes

    import psutil
    user32 = _user32()
    dwm = ctypes.windll.dwmapi  # type: ignore[attr-defined]
    out: list[dict] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd) > 0:
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            cloaked = wintypes.DWORD(0)
            if dwm.DwmGetWindowAttribute(hwnd, _DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)) != 0:
                cloaked.value = 0  # attribute not available: treat as shown
            exstyle = user32.GetWindowLongW(hwnd, _GWL_EXSTYLE)
            try:
                name = psutil.Process(pid.value).name()
            except psutil.Error:
                name = ""
            out.append({"hwnd": int(hwnd), "title": buf.value, "pid": pid.value, "process": name,
                        "cloaked": bool(cloaked.value), "tool": bool(exstyle & _WS_EX_TOOLWINDOW)})
        return True

    user32.EnumWindows(cb, 0)
    return out


def user_windows(raw: list[dict]) -> list[dict]:
    """The windows a person would see and count: not cloaked, not tool windows, not shell surfaces, not this
    program, and each title once (the top-most window with that title is kept)."""
    seen: set[str] = set()
    out = []
    for w in raw:
        title = " ".join(w["title"].split())
        if w.get("cloaked") or w.get("tool") or title in _SHELL_TITLES or w["pid"] == os.getpid():
            continue
        if title.casefold() in seen:
            continue
        seen.add(title.casefold())
        out.append({"hwnd": w["hwnd"], "title": title, "pid": w["pid"], "process": w["process"]})
    return out


def _enum() -> list[dict]:
    """Open app windows, top-most first: hwnd, title, pid, process name."""
    return user_windows(_raw_windows())


def list_windows() -> Result:
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Window management works on Windows only.")
    return Result.success({"windows": [{"title": w["title"], "app": w["process"]} for w in _enum()][:40]})


def find(query: str) -> dict | None:
    """The top-most window of the named app (by process name), else the top-most window whose title has the words."""
    from adhyaksh.nlu import entities
    from adhyaksh.tools import apps
    windows = _enum()
    key = entities.find_app(query) or entities.find_app(query, fuzzy=True)
    if key:
        # Store apps (Calculator, Snipping Tool) draw their visible frame in ApplicationFrameHost.exe: that window,
        # with the app's name in its title, is the one that can be minimised or maximised.
        for w in windows:
            if w["process"].casefold() == "applicationframehost.exe" and key.split()[0] in w["title"].casefold():
                return w
        names = apps.process_names(key, apps.allowlist().get(key, []))
        for w in windows:
            if w["process"].casefold() in names:
                return w
    words = [w for w in (query or "").casefold().split() if len(w) > 1]
    for w in windows:
        if words and all(word in w["title"].casefold() for word in words):
            return w
    return None


def state(hwnd: int) -> dict:
    user32 = _user32()
    if not user32.IsWindow(hwnd):
        return {"exists": False, "minimized": False, "maximized": False, "foreground": False}
    return {"exists": True, "minimized": bool(user32.IsIconic(hwnd)), "maximized": bool(user32.IsZoomed(hwnd)),
            "foreground": int(user32.GetForegroundWindow() or 0) == hwnd}


def _focus(hwnd: int) -> None:
    user32 = _user32()
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, _SW["restore"])
    user32.keybd_event(0x12, 0, 0, 0)  # a tap of Alt lets this program move another window to the front
    user32.SetForegroundWindow(hwnd)
    user32.keybd_event(0x12, 0, 2, 0)


def control(op: str, target: str = "", *, ctx: dict | None = None) -> Result:
    if op not in OPS:
        return Result.failure(E_BAD_ARGUMENTS, f"op must be one of: {', '.join(OPS)}.")
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Window management works on Windows only.")
    if op in _ALL:
        def go_all() -> Result:
            from adhyaksh.tools.display import powershell
            ok, _ = powershell(f"(New-Object -ComObject Shell.Application).{_ALL[op]}()")
            return Result.success({"op": op}) if ok else Result.failure(E_ACTION_FAILED, "Windows did not change the windows.")
        return policy.run_guarded("window_control", op.replace("_", " "), go_all, **_ctx(ctx))
    if not (target or "").strip():
        return Result.failure(E_BAD_ARGUMENTS, "Say which window: an app name or words from its title.")
    w = find(target)
    if w is None:
        return Result.failure(E_FILE_NOT_FOUND, f"No open window matches {target}.")

    def go() -> Result:
        hwnd = w["hwnd"]
        if op == "focus":
            _focus(hwnd)
        elif op == "close":
            _user32().PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE: the app may still ask to save
            time.sleep(0.5)
        else:
            _user32().ShowWindow(hwnd, _SW[op])
        return Result.success({"op": op, "hwnd": hwnd, "title": w["title"], "app": w["process"]})

    return policy.run_guarded("window_control", f"{op} {w['title'][:60]}", go, **_ctx(ctx))

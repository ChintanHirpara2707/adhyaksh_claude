"""System status (CPU, RAM, disk), screenshots, web opening and special folders."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED, Result
from adhyaksh.safety import policy

_CACHE: dict = {"at": 0.0, "data": None}
MIN_INTERVAL = 5.0


def status(*, ctx: dict | None = None) -> Result:
    ctx = ctx or {}

    def go() -> Result:
        try:
            import psutil
        except ImportError:
            return Result.failure(E_ACTION_FAILED, "psutil is not installed.")
        if _CACHE["data"] is None or time.monotonic() - _CACHE["at"] >= MIN_INTERVAL:
            usage = shutil.disk_usage(Path.home().anchor or "/")
            _CACHE.update(at=time.monotonic(), data={
                "cpu": psutil.cpu_percent(interval=0.2), "ram": psutil.virtual_memory().percent,
                "disk": usage.used / usage.total * 100})
        return Result.success(dict(_CACHE["data"]))

    return policy.run_guarded("system_status", "system", go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""))


def screenshot(*, ctx: dict | None = None) -> Result:
    """Take a screenshot with PIL and save it in the default work folder."""
    ctx = ctx or {}
    base = Path((ctx or {}).get("base") or config.get("default_work_folder"))

    def go() -> Result:
        try:
            from PIL import ImageGrab
        except ImportError:
            return Result.failure(E_ACTION_FAILED, "Screenshot is not available (Pillow is not installed).")
        try:
            img = ImageGrab.grab()
        except Exception as exc:  # pragma: no cover - environment dependent
            return Result.failure(E_ACTION_FAILED, f"Could not take a screenshot: {exc}.")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = base / f"screenshot_{stamp}.png"
        try:
            base.mkdir(parents=True, exist_ok=True)
            img.save(out, format="PNG")
        except (OSError, PermissionError) as exc:
            return Result.failure(E_ACTION_FAILED, f"Could not save the screenshot: {exc}.")
        return Result.success({"path": str(out)})

    return policy.run_guarded("screenshot", "screenshot", go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""))


def web_open(url: str, *, ctx: dict | None = None) -> Result:
    """Open a URL in the default browser. No allow-list is needed for browsers or websites."""
    ctx = ctx or {}
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    def go() -> Result:
        if os.environ.get("ADHYAKSH_NO_OPEN"):
            return Result.success({"url": url, "opened": False, "note": "open disabled in tests"})
        try:
            if os.name == "nt":
                os.startfile(url)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
            return Result.success({"url": url, "opened": True})
        except (OSError, AttributeError) as exc:
            return Result.failure(E_ACTION_FAILED, f"Could not open the browser: {exc}.")

    return policy.run_guarded("web_open", url, go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""))


def open_special_folder(name: str, *, ctx: dict | None = None) -> Result:
    """Open a Windows special folder (Recycle Bin, Downloads, Documents, Desktop)."""
    ctx = ctx or {}
    folders = config.default_special_folders()
    aliases = {"file manager": "explorer", "file explorer": "explorer", "explorer": "explorer"}
    key = (name or "").strip().casefold()
    key = aliases.get(key, key)
    target = folders.get(key)
    if target is None:
        return Result.failure(E_ACTION_FAILED, f"Unknown special folder: {name}.")

    def go() -> Result:
        if os.environ.get("ADHYAKSH_NO_OPEN"):
            return Result.success({"folder": name, "target": target, "opened": False,
                                   "note": "open disabled in tests"})
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return Result.success({"folder": name, "target": target, "opened": True})
        except (OSError, AttributeError) as exc:
            return Result.failure(E_ACTION_FAILED, f"Could not open {name}: {exc}.")

    return policy.run_guarded("special_folder_open", target, go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""))

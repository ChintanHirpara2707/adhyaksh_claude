"""Clipboard text read (L0) and write (L1) through safety.policy.run_guarded.

Windows uses the Win32 clipboard API through ctypes (no extra package); other systems fall back to tkinter.
"""
from __future__ import annotations

import os

from adhyaksh.result import E_ACTION_FAILED, Result
from adhyaksh.safety import policy

MAX_CHARS = 5000
CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def _ctx(ctx: dict | None) -> dict:
    return {"user_text": (ctx or {}).get("user_text", ""), "intent": (ctx or {}).get("intent", "")}


def _win():
    import ctypes
    from ctypes import wintypes
    u, k = ctypes.WinDLL("user32", use_last_error=True), ctypes.WinDLL("kernel32", use_last_error=True)
    u.OpenClipboard.argtypes, u.OpenClipboard.restype = [wintypes.HWND], wintypes.BOOL
    u.CloseClipboard.restype = wintypes.BOOL
    u.EmptyClipboard.restype = wintypes.BOOL
    u.GetClipboardData.argtypes, u.GetClipboardData.restype = [wintypes.UINT], wintypes.HANDLE
    u.SetClipboardData.argtypes, u.SetClipboardData.restype = [wintypes.UINT, wintypes.HANDLE], wintypes.HANDLE
    u.IsClipboardFormatAvailable.argtypes, u.IsClipboardFormatAvailable.restype = [wintypes.UINT], wintypes.BOOL
    k.GlobalAlloc.argtypes, k.GlobalAlloc.restype = [wintypes.UINT, ctypes.c_size_t], wintypes.HGLOBAL
    k.GlobalLock.argtypes, k.GlobalLock.restype = [wintypes.HGLOBAL], wintypes.LPVOID
    k.GlobalUnlock.argtypes, k.GlobalUnlock.restype = [wintypes.HGLOBAL], wintypes.BOOL
    k.GlobalFree.argtypes, k.GlobalFree.restype = [wintypes.HGLOBAL], wintypes.HGLOBAL
    return ctypes, u, k


def _open(u) -> bool:
    import time
    for _ in range(10):  # another program may hold the clipboard for a moment
        if u.OpenClipboard(None):
            return True
        time.sleep(0.05)
    return False


def get_text() -> str:
    if os.name == "nt":
        ctypes, u, k = _win()
        if not _open(u):
            raise OSError("The clipboard is in use by another program.")
        try:
            if not u.IsClipboardFormatAvailable(CF_UNICODETEXT):
                return ""
            h = u.GetClipboardData(CF_UNICODETEXT)
            if not h:
                return ""
            p = k.GlobalLock(h)
            try:
                return ctypes.wstring_at(p) if p else ""
            finally:
                k.GlobalUnlock(h)
        finally:
            u.CloseClipboard()
    import tkinter
    r = tkinter.Tk()
    r.withdraw()
    try:
        return r.clipboard_get()
    except tkinter.TclError:
        return ""
    finally:
        r.destroy()


def set_text(text: str) -> None:
    if os.name == "nt":
        ctypes, u, k = _win()
        data = ctypes.create_unicode_buffer(text)
        size = ctypes.sizeof(data)
        h = k.GlobalAlloc(GMEM_MOVEABLE, size)
        if not h:
            raise OSError("Out of memory for the clipboard.")
        p = k.GlobalLock(h)
        ctypes.memmove(p, data, size)
        k.GlobalUnlock(h)
        if not _open(u):
            k.GlobalFree(h)
            raise OSError("The clipboard is in use by another program.")
        try:
            u.EmptyClipboard()
            if not u.SetClipboardData(CF_UNICODETEXT, h):
                k.GlobalFree(h)
                raise OSError("The clipboard could not be set.")
        finally:
            u.CloseClipboard()
        return
    import tkinter
    r = tkinter.Tk()
    r.withdraw()
    r.clipboard_clear()
    r.clipboard_append(text)
    r.update()
    r.destroy()


def read(*, ctx: dict | None = None) -> Result:
    def go() -> Result:
        try:
            text = get_text()
        except Exception as exc:  # clipboard busy or unavailable
            return Result.failure(E_ACTION_FAILED, f"Could not read the clipboard ({exc}).")
        return Result.success({"text": text[:MAX_CHARS], "truncated": len(text) > MAX_CHARS, "empty": not text.strip()})
    return policy.run_guarded("clipboard_read", "clipboard", go, **_ctx(ctx))


def write(text: str, *, ctx: dict | None = None) -> Result:
    text = str(text or "")[:MAX_CHARS]
    if not text.strip():
        return Result.failure(E_ACTION_FAILED, "There is no text to copy.")

    def go() -> Result:
        try:
            set_text(text)
        except Exception as exc:
            return Result.failure(E_ACTION_FAILED, f"Could not write to the clipboard ({exc}).")
        return Result.success({"text": text})
    return policy.run_guarded("clipboard_write", text[:60], go, **_ctx(ctx))

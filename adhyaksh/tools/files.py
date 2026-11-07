"""File manager. Every function goes through safety.policy.run_guarded and returns a Result.

ctx (optional dict): user_text, intent, token (confirmation), allowed_roots, base.
"""
from __future__ import annotations

import re
import shutil
import time
from pathlib import Path
from typing import Callable

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED, E_FILE_NOT_FOUND, Result
from adhyaksh.safety import policy

MAX_READ_BYTES = 1_000_000
MAX_SHOWN_CHARS = 20_000
_BAD_NAME = re.compile(r'[<>:"|?*\x00-\x1f]')


def sanitize_name(name: str) -> str:
    """Return a safe file name or raise ValueError."""
    name = (name or "").strip()
    if not name or len(name) > 120 or _BAD_NAME.search(name) or name in (".", ".."):
        raise ValueError("Invalid file name.")
    return name


def run(action: str, target: str, make_runner: Callable[[Path | None], Callable[[], Result]],
        ctx: dict | None = None) -> Result:
    """Resolve target, then execute through the safety gateway."""
    ctx = ctx or {}
    roots = ctx.get("allowed_roots") if ctx.get("allowed_roots") is not None else config.get_allowed_roots()
    base = ctx.get("base") or Path(config.get("default_work_folder"))
    resolved, _ = policy.check_path(target, roots, base)
    shown = str(resolved) if resolved else target
    return policy.run_guarded(action, shown, make_runner(resolved), user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""), token=ctx.get("token"), allowed_roots=roots, base=base)


def default_folder(ctx: dict | None) -> str:
    return str((ctx or {}).get("base") or config.get("default_work_folder"))


def create(path: str, content: str = "", *, ctx: dict | None = None) -> Result:
    def make(p):
        def go():
            sanitize_name(p.name)
            if p.exists():
                return Result.failure(E_ACTION_FAILED, "The file already exists.")
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return Result.success({"path": str(p)})
        return go
    return run("file_create", path, make, ctx)


def create_folder(folder: str, *, ctx: dict | None = None) -> Result:
    """Create a folder inside an allowed root only (L1, no confirmation)."""
    def make(p):
        def go():
            sanitize_name(p.name)
            if p.exists():
                return Result.failure(E_ACTION_FAILED, "The folder already exists.")
            p.mkdir(parents=True, exist_ok=True)
            return Result.success({"path": str(p)})
        return go
    return run("file_create", folder, make, ctx)


def read(path: str, *, ctx: dict | None = None) -> Result:
    def make(p):
        def go():
            if not p.is_file():
                return Result.failure(E_FILE_NOT_FOUND, "The file was not found.")
            if p.stat().st_size > MAX_READ_BYTES:
                return Result.failure(E_ACTION_FAILED, "The file is larger than 1 MB.")
            text = p.read_text(encoding="utf-8", errors="replace")
            return Result.success({"path": str(p), "content": text[:MAX_SHOWN_CHARS]})
        return go
    return run("file_read", path, make, ctx)


def update(path: str, content: str, mode: str = "append", *, ctx: dict | None = None) -> Result:
    """mode 'append' is L1; mode 'overwrite' is L2 and needs confirmation."""
    action = "file_overwrite" if mode == "overwrite" else "file_append"

    def make(p):
        def go():
            if not p.is_file():
                return Result.failure(E_FILE_NOT_FOUND, "The file was not found.")
            if mode == "overwrite":
                p.write_text(content, encoding="utf-8")
            else:
                existing = p.read_text(encoding="utf-8", errors="replace")
                sep = "" if not existing or existing.endswith("\n") else "\n"
                p.write_text(existing + sep + content + "\n", encoding="utf-8")
            return Result.success({"path": str(p)})
        return go
    return run(action, path, make, ctx)


def _trash(p: Path) -> str:
    try:
        from send2trash import send2trash
        send2trash(str(p))
        return "recycle_bin"
    except ImportError:  # send2trash missing: keep the file recoverable in a local folder
        dest = config.data_dir() / "trash_fallback"
        dest.mkdir(parents=True, exist_ok=True)
        shutil.move(str(p), str(dest / f"{int(time.time())}_{p.name}"))
        return "local_trash_folder"


def delete(path: str, *, ctx: dict | None = None) -> Result:
    def make(p):
        def go():
            if not p.is_file():
                return Result.failure(E_FILE_NOT_FOUND, "The file was not found.")
            where = _trash(p)
            return Result.success({"path": str(p), "moved_to": where})
        return go
    return run("file_delete", path, make, ctx)


def search(query: str, folder: str | None = None, limit: int = 50, *, ctx: dict | None = None) -> Result:
    def make(p):
        def go():
            if not p.is_dir():
                return Result.success({"matches": []})
            q = query.casefold()
            found = [str(f) for f in sorted(p.rglob("*")) if f.is_file() and q in f.name.casefold()]
            return Result.success({"matches": found[:limit]})
        return go
    return run("file_search", folder or default_folder(ctx), make, ctx)


def list_dir(path: str | None = None, *, ctx: dict | None = None) -> Result:
    def make(p):
        def go():
            if not p.is_dir():
                return Result.failure(E_FILE_NOT_FOUND, "The folder was not found.")
            items = [{"name": f.name, "is_dir": f.is_dir(), "size": f.stat().st_size if f.is_file() else 0}
                     for f in sorted(p.iterdir())]
            return Result.success({"path": str(p), "items": items})
        return go
    return run("file_list", path or default_folder(ctx), make, ctx)

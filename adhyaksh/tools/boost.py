"""PC performance tools: stats, temp scan and temp clean using psutil."""
from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path

import psutil

from adhyaksh.safety import audit


def stats() -> dict:
    """Return current CPU, RAM and disk stats for the system drive."""
    cpu_percent = psutil.cpu_percent(interval=0.2)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(os.path.abspath(os.sep))
    return {
        "cpu_percent": float(cpu_percent),
        "ram_percent": float(mem.percent),
        "ram_available_gb": float(mem.available) / (1024 ** 3),
        "disk_percent": float(disk.percent),
        "disk_free_gb": float(disk.free) / (1024 ** 3),
    }


def _iter_regular_files(root: Path):
    """Yield regular files under root, skipping symlinks and errors."""
    try:
        entries = list(root.iterdir())
    except (OSError, PermissionError):
        return
    for entry in entries:
        try:
            if entry.is_symlink():
                continue
            if entry.is_dir():
                yield from _iter_regular_files(entry)
            elif entry.is_file():
                yield entry
        except (OSError, PermissionError):
            continue


def scan_temp(dir=None, min_age_hours: int = 24) -> dict:
    """Count regular files older than min_age_hours under dir (default temp dir).

    Returns {"files": n, "bytes": b}.
    """
    if dir is None:
        dir = tempfile.gettempdir()
    root = Path(dir)
    if not root.exists() or not root.is_dir():
        return {"files": 0, "bytes": 0}
    cutoff = time.time() - min_age_hours * 3600
    count = 0
    total = 0
    for entry in _iter_regular_files(root):
        try:
            if entry.stat().st_mtime < cutoff:
                count += 1
                total += entry.stat().st_size
        except (OSError, PermissionError):
            continue
    return {"files": count, "bytes": total}


def clean_temp(dir=None, min_age_hours: int = 24) -> dict:
    """Delete regular files older than min_age_hours under dir, then empty subfolders.

    Returns {"deleted": n, "freed_bytes": b, "skipped": n}.
    Skips locked/active files silently. Never touches anything outside dir.
    """
    if dir is None:
        dir = tempfile.gettempdir()
    root = Path(dir)
    if not root.exists() or not root.is_dir():
        return {"deleted": 0, "freed_bytes": 0, "skipped": 0}
    cutoff = time.time() - min_age_hours * 3600
    deleted = 0
    freed = 0
    skipped = 0
    for entry in _iter_regular_files(root):
        try:
            st = entry.stat()
        except (OSError, PermissionError):
            skipped += 1
            continue
        if st.st_mtime >= cutoff:
            continue
        try:
            freed += st.st_size
            entry.unlink()
            deleted += 1
        except (OSError, PermissionError):
            skipped += 1
    # Remove empty subfolders (bottom-up).
    for entry in sorted(root.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        try:
            if entry.is_dir() and not entry.is_symlink() and not any(entry.iterdir()):
                entry.rmdir()
        except (OSError, PermissionError):
            continue
    # Audit log entry as an L2 action.
    try:
        audit.record(
            user_text="clean_temp",
            intent="clean_temp",
            action="clean_temp",
            target=str(root),
            level=2,
            confirmed="confirmed",
            result=f"deleted={deleted}, freed_bytes={freed}, skipped={skipped}",
        )
    except Exception:
        pass
    return {"deleted": deleted, "freed_bytes": freed, "skipped": skipped}

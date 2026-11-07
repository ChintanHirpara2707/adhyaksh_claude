"""Excel and Word creation. Files are created in the default work folder, never overwritten."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED, Result
from adhyaksh.tools import files

INDIAN_NAMES = ["Aarav Sharma", "Priya Patel", "Rohan Mehta", "Ananya Iyer", "Vikram Singh", "Hiral Shah",
                "Karan Joshi", "Meera Nair", "Rahul Verma", "Pooja Desai", "Arjun Reddy", "Neha Gupta",
                "Siddharth Rao", "Kavya Menon", "Amit Trivedi", "Riya Kapoor", "Jay Thakkar", "Sneha Kulkarni"]


def open_default(path: Path) -> bool:
    """Open a file with the operating system default application. Never raises."""
    if os.environ.get("ADHYAKSH_NO_OPEN"):
        return False
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
        return True
    except (OSError, AttributeError):
        return False


def _unique(p: Path) -> Path:
    n, cand = 1, p
    while cand.exists():
        cand = p.with_name(f"{p.stem}_{n}{p.suffix}")
        n += 1
    return cand


def _target(name: str, ext: str, ctx: dict | None) -> str:
    name = files.sanitize_name(name)
    if not name.lower().endswith(ext):
        name += ext
    return name


def create_workbook(name: str, rows: list[list], *, open_after: bool = True, ctx: dict | None = None) -> Result:
    try:
        target = _target(name, ".xlsx", ctx)
    except ValueError as exc:
        return Result.failure(E_ACTION_FAILED, str(exc))

    def make(p):
        def go():
            from openpyxl import Workbook
            out = _unique(p)
            wb = Workbook()
            ws = wb.active
            for row in rows:
                ws.append(list(row))
            out.parent.mkdir(parents=True, exist_ok=True)
            wb.save(out)
            opened = open_after and open_default(out)
            return Result.success({"path": str(out), "rows": len(rows), "folder": str(out.parent), "opened": opened})
        return go
    return files.run("office_create", target, make, ctx)


def create_document(name: str, paragraphs: list[str], *, open_after: bool = True, ctx: dict | None = None) -> Result:
    try:
        target = _target(name, ".docx", ctx)
    except ValueError as exc:
        return Result.failure(E_ACTION_FAILED, str(exc))

    def make(p):
        def go():
            from docx import Document
            out = _unique(p)
            doc = Document()
            for para in paragraphs:
                doc.add_paragraph(para)
            out.parent.mkdir(parents=True, exist_ok=True)
            doc.save(out)
            opened = open_after and open_default(out)
            return Result.success({"path": str(out), "folder": str(out.parent), "opened": opened})
        return go
    return files.run("office_create", target, make, ctx)


def names_example(count: int = 5, *, ctx: dict | None = None) -> Result:
    """'open Excel and write 5 Indian names in 5 rows' without any LLM."""
    count = max(1, min(count, len(INDIAN_NAMES)))
    return create_workbook("names.xlsx", [[n] for n in INDIAN_NAMES[:count]], ctx=ctx)

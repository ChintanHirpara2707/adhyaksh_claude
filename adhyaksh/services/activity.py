"""Service layer for the Activity page: the audit log as readable, filterable rows.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime

from adhyaksh.safety import audit

LEVELS = {0: "L0 read-only", 1: "L1 reversible", 2: "L2 needs confirmation", 3: "L3 blocked"}
OUTCOMES = ["done", "failed", "blocked", "cancelled", "rejected"]

audit_list_recent = audit.list_recent


def outcome(result: str) -> str:
    r = (result or "").lower()
    if r == "ok":
        return "done"
    for word in ("blocked", "cancelled", "rejected"):
        if r.startswith(word):
            return word
    return "failed"  # "failed: ..." and "error: ..."


def _local_time(ts: str) -> str:
    try:
        return datetime.fromisoformat(ts).astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return ts or ""


def rows(limit: int = 500) -> list[dict]:
    """Newest first, with readable columns."""
    out = []
    for r in audit.list_recent(limit):
        out.append({"Time": _local_time(r.get("ts", "")), "Action": (r.get("action") or "").replace("_", " "),
                    "Target": r.get("target") or "", "Level": LEVELS.get(r.get("level"), str(r.get("level"))),
                    "Confirmed": r.get("confirmed") or "", "Outcome": outcome(r.get("result", "")),
                    "Result": r.get("result") or ""})
    return out


def filter_rows(items: list[dict], outcomes: list[str] | None = None, search: str = "") -> list[dict]:
    s = (search or "").strip().lower()
    keep = []
    for r in items:
        if outcomes and r["Outcome"] not in outcomes:
            continue
        if s and s not in (r["Action"] + " " + r["Target"] + " " + r["Result"]).lower():
            continue
        keep.append(r)
    return keep


def summary(items: list[dict]) -> dict:
    out = {k: 0 for k in OUTCOMES}
    for r in items:
        out[r["Outcome"]] = out.get(r["Outcome"], 0) + 1
    return out


def to_csv(items: list[dict]) -> bytes:
    buf = io.StringIO()
    if items:
        w = csv.DictWriter(buf, fieldnames=list(items[0]))
        w.writeheader()
        w.writerows(items)
    return buf.getvalue().encode("utf-8")

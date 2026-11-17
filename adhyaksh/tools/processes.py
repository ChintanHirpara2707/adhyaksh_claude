"""Process monitor: top programs by memory or CPU, and ending a program with confirmation.

Listing is L0. Ending processes is L2 (needs confirmation) and goes through safety.policy.run_guarded. System
processes and this assistant itself are never ended (refused at L3 and audited).
"""
from __future__ import annotations

import os
import time
from collections import defaultdict

from adhyaksh.result import E_ACTION_FAILED, E_FILE_NOT_FOUND, Result
from adhyaksh.safety import policy

# Windows core processes: ending them can crash or log out the session.
PROTECTED = {"system", "system idle process", "registry", "memory compression", "secure system", "smss.exe", "csrss.exe",
             "wininit.exe", "winlogon.exe", "services.exe", "lsass.exe", "lsaiso.exe", "svchost.exe", "dwm.exe", "explorer.exe",
             "fontdrvhost.exe", "sihost.exe", "spoolsv.exe", "msmpeng.exe", "nissrv.exe", "securityhealthservice.exe",
             "ctfmon.exe", "taskhostw.exe", "conhost.exe", "runtimebroker.exe", "searchindexer.exe", "audiodg.exe",
             "wudfhost.exe", "dllhost.exe", "init", "systemd", "launchd", "kernel_task", "loginwindow", "windowserver"}


def _ctx(ctx: dict | None) -> dict:
    return {"user_text": (ctx or {}).get("user_text", ""), "intent": (ctx or {}).get("intent", "")}


def _own_pids() -> set[int]:
    """This assistant and its parents (python, streamlit, the terminal that started it)."""
    import psutil
    pids = {os.getpid()}
    try:
        for p in psutil.Process(os.getpid()).parents():
            pids.add(p.pid)
    except psutil.Error:
        pass
    return pids


def snapshot(sample_seconds: float = 0.3) -> list[dict]:
    """All processes grouped by program name, with memory (MB, percent), CPU percent and process count."""
    import psutil
    procs = list(psutil.process_iter(["pid", "name", "memory_info", "memory_percent"]))
    for p in procs:
        try:
            p.cpu_percent(None)
        except psutil.Error:
            pass
    time.sleep(sample_seconds)
    groups: dict[str, dict] = defaultdict(lambda: {"count": 0, "ram_mb": 0.0, "ram_percent": 0.0, "cpu": 0.0, "pids": []})
    ncpu = psutil.cpu_count() or 1
    for p in procs:
        try:
            name = p.info["name"] or "?"
            g = groups[name]
            g["count"] += 1
            g["ram_mb"] += (p.info["memory_info"].rss if p.info["memory_info"] else 0) / (1024 * 1024)
            g["ram_percent"] += p.info["memory_percent"] or 0.0
            g["cpu"] += p.cpu_percent(None) / ncpu
            g["pids"].append(p.info["pid"])
        except (psutil.Error, AttributeError, TypeError):
            continue
    return [{"name": n, "count": g["count"], "ram_mb": round(g["ram_mb"], 1), "ram_percent": round(g["ram_percent"], 1),
             "cpu_percent": round(g["cpu"], 1), "pids": g["pids"], "protected": n.casefold() in PROTECTED}
            for n, g in groups.items()]


def list_processes(top: int = 10, sort: str = "memory", *, ctx: dict | None = None) -> Result:
    def go() -> Result:
        try:
            rows = snapshot()
        except ImportError:
            return Result.failure(E_ACTION_FAILED, "psutil is not installed.")
        key = "cpu_percent" if sort == "cpu" else "ram_mb"
        rows.sort(key=lambda r: r[key], reverse=True)
        top_rows = [{k: v for k, v in r.items() if k != "pids"} for r in rows[: max(1, min(int(top), 30))]]
        return Result.success({"sort": "cpu" if sort == "cpu" else "memory", "processes": top_rows, "total": len(rows)})
    return policy.run_guarded("process_list", "processes", go, **_ctx(ctx))


def _norm(name: str) -> str:
    n = str(name or "").strip().strip("\"'").casefold()
    return n[:-4] if n.endswith(".exe") else n


def resolve(target: str) -> tuple[list[dict], str]:
    """Process groups matching a name, a pid or 'heaviest'. Returns (groups, problem)."""
    rows = snapshot(0.05)
    t = str(target or "").strip()
    if not t:
        return [], "Which program should I end?"
    if t.isdigit():
        pid = int(t)
        hit = [dict(r, pids=[pid]) for r in rows if pid in r["pids"]]
        return hit, "" if hit else f"No process with id {pid} is running."
    if _norm(t) in ("heaviest", "biggest", "top", "largest"):
        free = [r for r in rows if not r["protected"] and not (set(r["pids"]) & _own_pids())]
        free.sort(key=lambda r: r["ram_mb"], reverse=True)
        return free[:1], "" if free else "No program can be ended."
    key = _norm(t)
    exact = [r for r in rows if _norm(r["name"]) == key]
    if exact:
        return exact, ""
    part = [r for r in rows if key and key in _norm(r["name"])]
    if len(part) == 1:
        return part, ""
    if len(part) > 1:
        return [], "More than one program matches: " + ", ".join(sorted({r['name'] for r in part})[:6]) + ". Please say the exact name."
    return [], f"No running program named {t} was found."


def kill_process(target: str, *, ctx: dict | None = None, token: str | None = None) -> Result:
    """End every process of one program (or one pid). L2: the first call returns a confirmation token."""
    try:
        groups, problem = resolve(str(target))
    except ImportError:
        return Result.failure(E_ACTION_FAILED, "psutil is not installed.")
    if problem:
        return Result.failure(E_FILE_NOT_FOUND, problem)
    g = groups[0]
    own = _own_pids()
    if g["protected"] or set(g["pids"]) & own:
        reason = "it is part of this assistant" if set(g["pids"]) & own else "it is a Windows system process"
        return policy.deny("process_kill", g["name"], f"{g['name']} cannot be ended because {reason}.", **_ctx(ctx))
    shown = f"{g['name']} ({len(g['pids'])} process{'es' if len(g['pids']) != 1 else ''}, {g['ram_mb']:.0f} MB)"

    def go() -> Result:
        import psutil
        procs = []
        for pid in g["pids"]:
            try:
                p = psutil.Process(pid)
                p.terminate()
                procs.append(p)
            except psutil.Error:
                continue
        gone, alive = psutil.wait_procs(procs, timeout=3)
        for p in alive:
            try:
                p.kill()
            except psutil.Error:
                pass
        if not procs:
            return Result.failure(E_ACTION_FAILED, f"{g['name']} could not be ended (it may need administrator rights).")
        return Result.success({"name": g["name"], "ended": len(procs), "freed_mb": round(g["ram_mb"])})
    return policy.run_guarded("process_kill", shown, go, token=token, **_ctx(ctx))

"""Watchdog of the background engine: notices about the PC, published on the event bus (the HUD shows them).

* battery low (at or below `watch_battery`, default 15 percent) while unplugged: once per drop;
* CPU at or above 90 percent for 2 minutes: once, with the busiest program; again only after it has calmed down;
* system drive almost full (under 5 percent free): at most once an hour;
* reminders that are due: each one once (reminders.due marks them fired, so the console and the engine never both
  announce the same reminder).
Reading only: the watchdog never changes anything on the PC.
"""
from __future__ import annotations

import logging
import os
import threading
import time

from adhyaksh import config, events, logging_setup

TICK_SECONDS = 15
CPU_HIGH, CPU_CALM, CPU_SUSTAIN_TICKS = 90.0, 70.0, 8  # 8 ticks of 15 s = 2 minutes
DISK_LOW_PERCENT_FREE = 5.0
DISK_REPEAT_SECONDS = 3600


class Watchdog:
    def __init__(self, readers: dict | None = None):
        self.readers = {"battery": _battery, "cpu": _cpu, "disk": _disk, "reminders": _reminders, "top": _top_process,
                        **(readers or {})}
        self.battery_warned = False
        self.cpu_high_ticks = 0
        self.cpu_warned = False
        self.disk_warned_at: float | None = None  # never warned yet

    def check(self, now: float | None = None) -> list[dict]:
        """One round of checks. Returns the notices raised (also published)."""
        now = time.time() if now is None else now
        notices: list[dict] = []
        try:
            notices += self._battery()
            notices += self._cpu()
            notices += self._disk(now)
            notices += [{"kind": "reminder", "text": f"Reminder: {r['text']}", "id": r["id"]} for r in self.readers["reminders"]()]
        except Exception as exc:  # a failing sensor must never stop the engine
            logging_setup.event("watchdog_error", logging.WARNING, error=type(exc).__name__)
        for n in notices:
            events.publish("notice", **n)
            logging_setup.event("watchdog_notice", kind=n["kind"])
        return notices

    def _battery(self) -> list[dict]:
        b = self.readers["battery"]()
        if not b or not b.get("present"):
            return []
        limit = int(config.get("watch_battery"))
        if b["plugged"] or b["percent"] > limit + 5:
            self.battery_warned = False  # re-arm once it charges or rises again
            return []
        if b["percent"] <= limit and not self.battery_warned:
            self.battery_warned = True
            return [{"kind": "battery", "text": f"Battery is at {b['percent']} percent. Plug in the charger."}]
        return []

    def _cpu(self) -> list[dict]:
        cpu = self.readers["cpu"]()
        if cpu >= CPU_HIGH:
            self.cpu_high_ticks += 1
        elif cpu < CPU_CALM:
            self.cpu_high_ticks, self.cpu_warned = 0, False
        if self.cpu_high_ticks >= CPU_SUSTAIN_TICKS and not self.cpu_warned:
            self.cpu_warned = True
            top = self.readers["top"]()
            return [{"kind": "cpu", "text": f"The CPU has been above {CPU_HIGH:.0f} percent for 2 minutes"
                     + (f", mostly {top}." if top else ".")}]
        return []

    def _disk(self, now: float) -> list[dict]:
        free = self.readers["disk"]()
        due = self.disk_warned_at is None or now - self.disk_warned_at >= DISK_REPEAT_SECONDS
        if free is not None and free < DISK_LOW_PERCENT_FREE and due:
            self.disk_warned_at = now
            return [{"kind": "disk", "text": f"The system drive has only {free:.0f} percent free space left."}]
        return []


def _battery() -> dict:
    from adhyaksh.tools import power
    return power.battery().data


def _cpu() -> float:
    import psutil
    return float(psutil.cpu_percent(interval=None))


def _disk() -> float | None:
    import psutil
    try:
        usage = psutil.disk_usage(os.environ.get("SystemDrive", "C:") + "\\" if os.name == "nt" else "/")
    except OSError:
        return None
    return 100.0 - usage.percent


def _reminders() -> list[dict]:
    from adhyaksh.tools import reminders
    return reminders.due()


def _top_process() -> str:
    import psutil
    best, name = 0.0, ""
    for p in psutil.process_iter(["name", "cpu_percent"]):
        if (p.info["cpu_percent"] or 0) > best and p.pid != os.getpid():
            best, name = p.info["cpu_percent"], p.info["name"] or ""
    return name


_thread: threading.Thread | None = None
_stop = threading.Event()


def start() -> None:
    """Run the checks every TICK_SECONDS in a daemon thread (the engine calls this once at start)."""
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    dog = Watchdog()

    def loop():
        while not _stop.wait(TICK_SECONDS):
            dog.check()
    _thread = threading.Thread(target=loop, name="adhyaksh-watchdog", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()

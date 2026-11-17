"""Closing apps by voice or text: no confirmation, finds the real process name, never loses unsaved work,
never ends File Explorer's taskbar or this program itself."""
import subprocess
import sys

import psutil

from adhyaksh import config
from adhyaksh.chat import context, engine
from adhyaksh.result import E_BLOCKED
from adhyaksh.safety import policy
from adhyaksh.tools import apps
from tests.helpers import fresh_env


class _FakeProc:
    def __init__(self, pid, name, alive_after_close=False):
        self.pid, self.info = pid, {"pid": pid, "name": name}
        self.alive, self.ended, self.alive_after_close = True, False, alive_after_close

    def is_running(self):
        return self.alive

    def status(self):
        return psutil.STATUS_RUNNING

    def terminate(self):
        self.alive, self.ended = False, True

    kill = terminate


def _fake_system(monkeypatch, procs, windows=None):
    """procs: fake processes; windows: pids that own a visible window (closing it ends the process
    unless alive_after_close, which stands for a save prompt)."""
    windows = set(windows or [])
    closed = []
    monkeypatch.setattr(psutil, "process_iter", lambda *a, **k: list(procs))
    monkeypatch.setattr(psutil, "wait_procs", lambda ps, timeout=None: ([p for p in ps if not p.alive], [p for p in ps if p.alive]))
    monkeypatch.setattr(apps, "_protected_pids", lambda: {1})
    by_pid = {p.pid: p for p in procs}

    def wins(pids=None, class_name=None):
        return [(1000 + pid, pid) for pid in sorted(windows) if pids and pid in pids and by_pid[pid].alive]

    def post(hwnds):
        for h in hwnds:
            p = by_pid[h - 1000]
            closed.append(p.pid)
            if not p.alive_after_close:
                p.alive = False
    monkeypatch.setattr(apps, "_windows", wins)
    monkeypatch.setattr(apps, "_post_close", post)
    return closed


def test_closing_needs_no_confirmation():
    assert policy.LEVELS["app_close"] == 1 and not policy.authorize("app_close", "notepad").needs_confirmation


def test_real_process_names_are_known():
    assert "calculatorapp.exe" in apps.process_names("calculator", ["calc.exe"])
    assert "code.exe" in apps.process_names("vs code", ["code"])
    assert "whatsapp.root.exe" in apps.process_names("whatsapp", ["WhatsApp.exe"])
    assert "python.exe" not in apps.process_names("sleeper", [sys.executable])  # interpreters: only what we launched


def test_calculator_launched_as_calc_exe_is_closed(monkeypatch):
    """The reported bug: calc.exe exits at once and CalculatorApp.exe keeps running."""
    fresh_env()
    calc, other = _FakeProc(50, "CalculatorApp.exe"), _FakeProc(51, "notepad.exe")
    _fake_system(monkeypatch, [calc, other])
    res = apps.close_app("calculator")
    assert res.ok and res.data["closed"] == 1 and calc.ended and other.alive


def test_windows_are_closed_politely_and_a_save_prompt_is_respected(monkeypatch):
    fresh_env()
    saved, unsaved = _FakeProc(60, "notepad.exe"), _FakeProc(61, "notepad.exe", alive_after_close=True)
    closed = _fake_system(monkeypatch, [saved, unsaved], windows={60, 61})
    res = apps.close_app("Notepad")
    assert res.ok and closed == [60, 61]
    assert not saved.alive and not saved.ended          # closed by WM_CLOSE, not killed
    assert unsaved.alive and not unsaved.ended          # left showing its save prompt
    assert res.data == {"app": "notepad", "closed": 1, "waiting": 1}


def test_this_program_is_never_ended(monkeypatch):
    fresh_env()
    me = _FakeProc(1, "chrome.exe")
    _fake_system(monkeypatch, [me])
    res = apps.close_app("chrome")
    assert not res.ok and "not running" in res.message and me.alive


def test_not_running_gives_a_clear_reply(monkeypatch):
    fresh_env()
    _fake_system(monkeypatch, [])
    r = engine.handle_message("close notepad", context.new_conversation()).data
    assert "notepad is not running" in r["reply"] and "No running instance" not in r["reply"]


def test_voice_style_close_replies_closed_without_asking(monkeypatch):
    fresh_env()
    _fake_system(monkeypatch, [_FakeProc(70, "chrome.exe")], windows={70})
    for text in ("chrome band karo", "chrome बंद करो", "close chrome"):
        r = engine.handle_message(text, context.new_conversation()).data
        assert r["reply"] == "Closed chrome." and "confirm" not in r["reply"].lower(), (text, r)
        _fake_system(monkeypatch, [_FakeProc(70, "chrome.exe")], windows={70})


def test_save_prompt_reply(monkeypatch):
    fresh_env()
    _fake_system(monkeypatch, [_FakeProc(80, "notepad.exe", alive_after_close=True)], windows={80})
    r = engine.handle_message("close notepad", context.new_conversation()).data
    assert "save prompt" in r["reply"]


def test_file_explorer_closes_windows_not_the_taskbar(monkeypatch):
    fresh_env()
    posted, ended = [], []
    monkeypatch.setattr(apps.os, "name", "nt")
    monkeypatch.setattr(apps, "_windows", lambda pids=None, class_name=None: [(5, 900), (6, 900)] if class_name == "CabinetWClass" else [])
    monkeypatch.setattr(apps, "_post_close", lambda hwnds: posted.extend(hwnds))
    monkeypatch.setattr(apps, "_close_processes", lambda *a: ended.append(a))
    res = apps.close_app("file explorer")
    assert res.ok and posted == [5, 6] and not ended


def test_launched_process_closes_and_unknown_app_is_refused():
    fresh_env()
    config.set_value("app_allowlist", '{"sleeper": ["%s", "-c", "import time; time.sleep(30)"]}' % sys.executable.replace("\\", "/"))
    assert apps.close_app("regedit").error_code == E_BLOCKED
    opened = apps.open_app("sleeper")
    assert opened.ok
    try:
        res = apps.close_app("sleeper")
        assert res.ok and res.data["closed"] == 1 and not psutil.pid_exists(opened.data["pid"]) or \
            psutil.Process(opened.data["pid"]).status() == psutil.STATUS_ZOMBIE
        assert not apps.close_app("sleeper").ok  # second close: not running
    finally:
        try:
            psutil.Process(opened.data["pid"]).kill()
        except psutil.Error:
            pass

"""P4 Cowork: reminder times, reminders, process monitor and safe ending, clipboard, multi-step requests."""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta

import pytest

from adhyaksh import config, db
from adhyaksh.chat import context, engine, router
from adhyaksh.result import E_BLOCKED, E_NEEDS_CONFIRM, Result
from adhyaksh.tools import clipboard, processes, reminders, when
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"
NOW = datetime(2026, 11, 17, 14, 30)


@pytest.mark.parametrize("text,due,repeat,what", [
    ("remind me to call mom at 6 pm", "2026-11-17 18:00", "none", "call mom"),
    ("set a reminder for tomorrow 9 am to pay the electricity bill", "2026-11-18 09:00", "none", "pay the electricity bill"),
    ("remind me in 20 minutes to check the oven", "2026-11-17 14:50", "none", "check the oven"),
    ("wake me up at 5:30 am", "2026-11-18 05:30", "none", "Wake up"),
    ("remind me every day at 8 pm to take medicine", "2026-11-17 20:00", "daily", "take medicine"),
    ("remind me at 11 to sleep", "2026-11-17 23:00", "none", "sleep"),           # 11 am has passed: 11 pm
    ("remind me at 2 to pick up the kids", "2026-11-18 14:00", "none", "pick up the kids"),  # 2 am and 2 pm passed
    ("मुझे शाम 5 बजे दवाई लेने की याद दिलाना", "2026-11-17 17:00", "none", "दवाई लेने"),
    ("कल सुबह 7 बजे का अलार्म लगा दो", "2026-11-18 07:00", "none", "Wake up"),
    ("મને સાંજે 6 વાગ્યે દૂધ લેવાનું યાદ અપાવજો", "2026-11-17 18:00", "none", "દૂધ લેવાનું"),
    ("mujhe 10 minute baad yaad dilana ki gas band karni hai", "2026-11-17 14:40", "none", "gas band karni hai"),
    ("mane 5 vage meeting nu yaad apavjo", "2026-11-17 17:00", "none", "meeting"),
    ("roz raat 10 baje phone charge karne ki yaad dilana", "2026-11-17 22:00", "daily", "phone charge karne"),
])
def test_reminder_times_and_text(text, due, repeat, what):
    w = when.parse(text, NOW)
    assert w.due.strftime("%Y-%m-%d %H:%M") == due and w.repeat == repeat, (text, w)
    assert when.reminder_text(text) == what, text


def test_no_time_means_ask():
    assert when.parse("remind me to call the bank", NOW).due is None


def test_reminders_store_fire_and_cancel():
    fresh_env()
    soon = (datetime.now() + timedelta(minutes=5)).strftime(reminders.FMT)
    a = reminders.add("call mom", soon).data
    b = reminders.add("take medicine", soon, "daily").data
    assert a["when"].startswith("today") or a["when"].startswith("tomorrow")
    assert [r["text"] for r in reminders.list_pending().data["reminders"]] == ["call mom", "take medicine"]
    assert reminders.due() == []
    fired = reminders.due(datetime.now() + timedelta(minutes=6))
    assert {f["text"] for f in fired} == {"call mom", "take medicine"}
    left = reminders.list_pending().data["reminders"]
    assert [r["text"] for r in left] == ["take medicine"] and left[0]["due"] > soon  # daily moved to the next day
    assert reminders.cancel("medicine").data["text"] == "take medicine" and not reminders.list_pending().data["reminders"]
    assert not reminders.add("x", "2001-01-01T10:00:00").ok  # in the past
    assert reminders.cancel(all_pending=True).message == "You have no pending reminders."
    reminders.add("a", soon), reminders.add("b", soon)
    assert reminders.cancel(all_pending=True).error_code == E_NEEDS_CONFIRM  # cancelling everything needs confirmation


def test_reminder_chat_flow_asks_for_time_and_lists():
    fresh_env()
    cid = context.new_conversation()
    say = lambda t: engine.handle_message(t, cid).data  # noqa: E731
    r = say("remind me to call the bank")
    assert r["reply"] == "When should I remind you?"
    r = say("tomorrow at 10 am")
    assert r["intent"] == "reminder_set" and "call the bank" in r["reply"] and "tomorrow at 10:00 AM" in r["reply"]
    assert "call the bank" in say("what reminders do i have")["reply"]
    assert "Cancelled the reminder: call the bank" in say("cancel the reminder about the bank")["reply"]
    assert say("show my reminders")["reply"] == "You have no pending reminders."
    r = say("set an alarm for 7 in the morning")
    assert "Wake up" in r["reply"] and "7:00 AM" in r["reply"]


def test_process_snapshot_and_protected_refusals(monkeypatch):
    fresh_env()
    rows = processes.list_processes(5).data
    assert rows["processes"] and rows["total"] >= 5 and all("pids" not in p for p in rows["processes"])
    me = os.path.basename(sys.executable)
    r = processes.kill_process(str(os.getpid()))
    assert r.error_code == E_BLOCKED and "part of this assistant" in r.message
    if os.name == "nt":
        r = processes.kill_process("csrss.exe")
        assert r.error_code == E_BLOCKED and "system process" in r.message
    assert "No running program" in processes.kill_process("definitely-not-running-xyz").message
    groups, _ = processes.resolve("heaviest")
    assert groups and not groups[0]["protected"] and os.getpid() not in groups[0]["pids"]
    rec = db.query_all("SELECT action, level, result FROM audit_log WHERE action='process_kill'")
    assert rec and all(x["level"] == 3 for x in rec)


def test_kill_a_real_child_process_only_after_confirmation():
    fresh_env()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        time.sleep(0.5)
        r = processes.kill_process(str(child.pid))
        assert r.error_code == E_NEEDS_CONFIRM and child.poll() is None  # nothing happens before confirmation
        done = processes.kill_process(str(child.pid), token=r.data["token"])
        assert done.ok and done.data["ended"] == 1
        child.wait(timeout=5)
        assert child.poll() is not None
    finally:
        if child.poll() is None:
            child.kill()


def test_process_chat_flow(monkeypatch):
    fresh_env()
    cid = context.new_conversation()
    r = engine.handle_message("top 3 apps by ram", cid).data
    assert r["intent"] == "process_list" and r["reply"].startswith("Top programs by memory") and r["reply"].count("\n") >= 3
    killed = []
    monkeypatch.setattr(processes, "resolve", lambda t: ([{"name": "zoom.exe", "pids": [99999], "ram_mb": 300.0, "protected": False}], ""))
    monkeypatch.setattr(processes, "_own_pids", lambda: {1})
    import psutil
    # Record terminate() calls (constructing a Process is not a kill; the post-condition check also looks the pid up).
    monkeypatch.setattr(psutil, "Process", lambda pid: type("P", (), {"terminate": lambda s: killed.append(pid), "kill": lambda s: None})())
    monkeypatch.setattr(psutil, "wait_procs", lambda procs, timeout=3: (procs, []))
    r = engine.handle_message("end task zoom", cid).data
    assert r["intent"] == "process_kill" and r["confirmation"] and "Unsaved work" in r["reply"] and not killed
    r = engine.handle_message("haan", cid).data
    assert killed == [99999] and "Ended zoom.exe" in r["reply"]


def test_clipboard_round_trip_and_chat(monkeypatch):
    fresh_env()
    try:
        before = clipboard.get_text()
    except Exception:
        pytest.skip("no clipboard in this environment")
    try:
        assert clipboard.write("ADHYAKSH clipboard test १२३").ok
        assert clipboard.read().data["text"] == "ADHYAKSH clipboard test १२३"
        cid = context.new_conversation()
        r = engine.handle_message('copy "see you at 5" to the clipboard', cid).data
        assert r["intent"] == "clipboard_write" and clipboard.get_text() == "see you at 5"
        r = engine.handle_message("what is on my clipboard", cid).data
        assert r["intent"] == "clipboard_read" and "see you at 5" in r["reply"]
        assert not clipboard.write("   ").ok
    finally:
        if before:
            clipboard.set_text(before)


def _ws():
    base = fresh_env()
    ws = base / "ws"
    ws.mkdir()
    config.set_value("allowed_folders", json.dumps([str(ws.resolve())]))
    config.set_value("default_work_folder", str(ws.resolve()))
    return ws.resolve()


def test_multi_step_runs_each_step_through_the_gateway():
    ws = _ws()
    cid = context.new_conversation()
    r = engine.handle_message('notes.txt banao aur usme "hello" likh do', cid).data
    assert r["intent"] == "multi_step" and (ws / "notes.txt").read_text(encoding="utf-8").strip() == "hello"
    r = engine.handle_message("make a folder Reports and create summary.txt", cid).data
    assert (ws / "Reports").is_dir() and (ws / "summary.txt").exists() and r["reply"].startswith("1. ")
    (ws / "old.txt").write_text("x", encoding="utf-8")
    r = engine.handle_message("delete old.txt and then create new.txt", cid).data
    assert r["confirmation"] and (ws / "old.txt").exists() and not (ws / "new.txt").exists()
    assert "Not done yet" in r["reply"] and "create new.txt" in r["reply"]
    from adhyaksh import db as _db
    assert _db.query_one("SELECT COUNT(*) AS n FROM audit_log WHERE action='file_create'")["n"] >= 2


@pytest.mark.parametrize("text", ["remember that i like tea and coffee", "search google for black and white movies",
                                  "create a file named a and b.txt", "what is the time then", "i was running late today and tired"])
def test_split_steps_leaves_single_requests_alone(text):
    assert router.split_steps(text) is None


def test_chat_mode_refuses_pc_control_but_allows_reminders():
    fresh_env()
    cid = context.new_conversation()
    assert engine.handle_message("show running processes", cid, mode="chat").data["action"] == "needs_cowork"
    assert engine.handle_message("what is on my clipboard", cid, mode="chat").data["action"] == "needs_cowork"
    assert engine.handle_message("remind me to stretch in 30 minutes", cid, mode="chat").data["intent"] == "reminder_set"


def test_confirmation_survives_a_change_in_memory_use(monkeypatch):
    """The yes must still match when the program's memory use or process count changed after the question."""
    fresh_env()
    from adhyaksh.result import E_CONFIRM_INVALID
    snaps = iter([[{"name": "fakeapp.exe", "count": 1, "ram_mb": 100.0, "ram_percent": 1.0, "cpu": 0.0, "pids": [999991], "protected": False}],
                  [{"name": "fakeapp.exe", "count": 2, "ram_mb": 180.0, "ram_percent": 2.0, "cpu": 0.0, "pids": [999991, 999992], "protected": False}]])
    monkeypatch.setattr(processes, "snapshot", lambda *a, **k: next(snaps))
    r = processes.kill_process("fakeapp")
    assert r.error_code == E_NEEDS_CONFIRM and r.data["target"] == "fakeapp.exe"
    done = processes.kill_process("fakeapp", token=r.data["token"])
    assert done.error_code != E_CONFIRM_INVALID  # the pids do not exist, so ending fails for that reason only

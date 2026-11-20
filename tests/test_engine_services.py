"""Phase 3a-3: watchdog notices, the console's client for the background engine, and starting with Windows.
Sensors, HTTP and the Startup folder are faked: nothing on the PC is read or changed."""
import pytest

from adhyaksh import autostart, client, config, events, watchdog
from adhyaksh.chat import context
from adhyaksh.result import Result
from adhyaksh.services import chat as chat_svc
from tests.helpers import fresh_env


@pytest.fixture(autouse=True)
def _env():
    fresh_env()
    events.reset()
    client.forget_cache()
    yield
    events.reset()
    client.forget_cache()


def _dog(**readers):
    base = {"battery": lambda: {"present": False}, "cpu": lambda: 10.0, "disk": lambda: 50.0, "reminders": lambda: [],
            "top": lambda: "chrome.exe"}
    return watchdog.Watchdog({**base, **readers})


# ---- watchdog -----------------------------------------------------------------------------------------------------
def test_battery_warns_once_per_drop_and_rearms():
    level = {"percent": 14, "plugged": False}
    dog = _dog(battery=lambda: {"present": True, **level})
    assert [n["kind"] for n in dog.check()] == ["battery"]
    assert dog.check() == []  # still low: no repeat
    level.update(plugged=True)
    dog.check()
    level.update(plugged=False, percent=12)
    assert [n["kind"] for n in dog.check()] == ["battery"]


def test_cpu_must_stay_high_for_two_minutes():
    cpu = {"v": 95.0}
    dog = _dog(cpu=lambda: cpu["v"])
    raised = [dog.check() for _ in range(watchdog.CPU_SUSTAIN_TICKS)]
    assert all(r == [] for r in raised[:-1]) and "mostly chrome.exe" in raised[-1][0]["text"]
    assert dog.check() == []  # once
    cpu["v"] = 50.0
    dog.check()
    cpu["v"] = 95.0
    assert all(dog.check() == [] for _ in range(watchdog.CPU_SUSTAIN_TICKS - 1))


def test_disk_warning_at_most_hourly():
    dog = _dog(disk=lambda: 3.0)
    assert dog.check(now=1000.0)[0]["kind"] == "disk"
    assert dog.check(now=1000.0 + 600) == []
    assert dog.check(now=1000.0 + watchdog.DISK_REPEAT_SECONDS)[0]["kind"] == "disk"


def test_reminders_become_notices_on_the_bus():
    q = events.subscribe()
    _dog(reminders=lambda: [{"id": 7, "text": "call mom"}]).check()
    e = q.get_nowait()
    assert e["type"] == "notice" and e["kind"] == "reminder" and e["text"] == "Reminder: call mom"


def test_a_broken_sensor_never_stops_the_watchdog():
    dog = _dog(battery=lambda: 1 / 0)
    assert dog.check() == []


def test_real_due_reminders_fire_once():
    from datetime import datetime, timedelta

    from adhyaksh import db
    from adhyaksh.tools import reminders
    past = (datetime.now() - timedelta(minutes=1)).strftime(reminders.FMT)  # add() rightly refuses a time in the past
    db.execute("INSERT INTO reminders(text,due_at,repeat,status,created_at) VALUES(?,?,?,?,?)",
               ("drink water", past, "none", "pending", db.utcnow()))
    assert [n["text"] for n in watchdog.Watchdog({"battery": lambda: {}, "cpu": lambda: 0.0, "disk": lambda: 50.0}).check()] \
        == ["Reminder: drink water"]
    assert watchdog._reminders() == []


# ---- console client ---------------------------------------------------------------------------------------------------
def test_no_engine_means_everything_runs_here(monkeypatch):
    calls = []
    monkeypatch.setattr(client, "_call", lambda *a, **k: calls.append(a) or Result.success({}))
    cid = context.new_conversation()
    r = chat_svc.engine_handle_message("what is 2 + 3", cid)
    assert "5" in r.data["reply"] and not calls  # the health check failed: nothing was sent anywhere


def test_with_the_engine_running_the_console_uses_it(monkeypatch):
    monkeypatch.setattr(client, "available", lambda: True)
    sent = []
    monkeypatch.setattr(client, "_call", lambda m, p, b=None, timeout=120.0: sent.append((m, p, b)) or Result.success(
        {"reply": "from the engine", "pending": {"token": "t", "action": "file_delete", "target": "a.txt"}}))
    assert chat_svc.engine_handle_message("hello", 5).data["reply"] == "from the engine"
    assert chat_svc.engine_confirm(5, True).ok
    assert chat_svc.pending_confirm(5) == {"token": "t", "action": "file_delete", "target": "a.txt"}
    assert [s[1] for s in sent] == ["/v1/message", "/v1/confirm", "/v1/pending/5"]


def test_attachments_always_stay_in_this_process(monkeypatch):
    monkeypatch.setattr(client, "available", lambda: True)
    sent = []
    monkeypatch.setattr(client, "_call", lambda *a, **k: sent.append(a) or Result.success({}))
    chat_svc.engine_handle_message("read this", context.new_conversation(), attachments=[("a.txt", b"hello")])
    assert not sent


def test_engine_gone_mid_session_falls_back_here(monkeypatch):
    from adhyaksh.result import E_NETWORK
    monkeypatch.setattr(client, "available", lambda: True)
    monkeypatch.setattr(client, "_call", lambda *a, **k: Result.failure(E_NETWORK, "down"))
    assert "5" in chat_svc.engine_handle_message("what is 2 + 3", context.new_conversation()).data["reply"]


def test_setting_off_never_contacts_the_engine(monkeypatch):
    config.set_value("background_engine", "off")
    import requests
    monkeypatch.setattr(requests, "get", lambda *a, **k: (_ for _ in ()).throw(AssertionError("contacted")))
    assert client.available() is False


def test_client_only_talks_to_loopback():
    assert client._url("/v1/health").startswith("http://127.0.0.1:")


# ---- start with Windows -------------------------------------------------------------------------------------------------
def test_autostart_writes_and_removes_one_file(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    folder = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    folder.mkdir(parents=True)
    monkeypatch.setattr(autostart.os, "name", "nt")
    assert not autostart.enabled()
    res = autostart.enable()
    text = (folder / autostart.FILE_NAME).read_text(encoding="utf-8")
    assert res.ok and autostart.enabled() and "-m adhyaksh.server" in text and "/min" in text
    assert autostart.disable().ok and not autostart.enabled() and list(folder.iterdir()) == []


def test_settings_page_renders_the_engine_section():
    from pathlib import Path

    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app_pages" / "settings.py"), default_timeout=60).run()
    assert not at.exception
    assert any("Engine: not running" in c.value for c in at.caption)
    assert any("Start the engine when Windows starts" == t.label for t in at.toggle)

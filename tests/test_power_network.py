"""Phase 2b-2: Wi-Fi and Bluetooth, battery, lock, sleep, restart, shut down. PowerShell, subprocess and the lock
call are faked: tests never switch a radio, lock the PC or schedule a shutdown."""
import pytest

from adhyaksh.chat import context, engine
from adhyaksh.nlu import frames
from adhyaksh.result import E_ACTION_FAILED, E_BAD_ARGUMENTS, E_NEEDS_CONFIRM
from adhyaksh.safety import policy
from adhyaksh.tools import network, power
from tests.helpers import fresh_env


@pytest.fixture
def radios(monkeypatch):
    fresh_env()
    state = {"WiFi": "On", "Bluetooth": "Off", "scripts": [], "access": "Allowed"}

    def fake_ps(script, timeout=15.0):
        state["scripts"].append(script)
        if "SetStateAsync" in script:
            if state["access"] != "Allowed":
                return True, f"denied|{state['access']}"
            kind = "WiFi" if "'WiFi'" in script else "Bluetooth"
            state[kind] = "On" if "SetStateAsync('On')" in script else "Off"
            return True, "result|Allowed"
        return True, f"WiFi|{state['WiFi']}\nBluetooth|{state['Bluetooth']}"
    monkeypatch.setattr(network, "powershell", fake_ps)
    monkeypatch.setattr(network.os, "name", "nt")
    monkeypatch.setattr(network, "wifi_details", lambda: {"ssid": "HomeNet", "signal": "88"})
    return state


@pytest.fixture
def pc(monkeypatch):
    fresh_env()
    ran = []
    monkeypatch.setattr(power.os, "name", "nt")
    monkeypatch.setattr(power, "_run", lambda cmd: ran.append(cmd) or True)
    monkeypatch.setattr(power, "_lock", lambda: ran.append(["lock"]) or True)
    return ran


# ---- radios ---------------------------------------------------------------------------------------------------
def test_read_radio_state(radios):
    assert network.status().data == {"wifi": True, "bluetooth": False, "wifi_network": {"ssid": "HomeNet", "signal": "88"}}


def test_turning_a_radio_on_is_immediate_and_verified(radios):
    res = network.set_radio("bluetooth", True)
    assert res.ok and res.data["verified"] is True and radios["Bluetooth"] == "On"


def test_turning_a_radio_off_needs_confirmation(radios):
    pending = network.set_radio("wifi", False)
    assert pending.error_code == E_NEEDS_CONFIRM and radios["WiFi"] == "On"
    done = network.set_radio("wifi", False, ctx={"token": pending.data["token"]})
    assert done.ok and radios["WiFi"] == "Off"


def test_windows_refusal_is_reported_not_faked(radios):
    radios["access"] = "DeniedBySystem"
    res = network.set_radio("bluetooth", True)
    assert res.error_code == E_ACTION_FAILED and "did not allow" in res.message and radios["Bluetooth"] == "Off"


def test_the_radio_script_only_gets_fixed_tokens(radios):
    network.set_radio("bluetooth", True)
    script = radios["scripts"][-2]
    assert "Kind -eq 'Bluetooth'" in script and "SetStateAsync('On')" in script
    assert network.set_radio("wifi; Remove-Item C:/", True).error_code == E_BAD_ARGUMENTS
    assert network.set_radio("wifi", "yes").error_code == E_BAD_ARGUMENTS


# ---- power -----------------------------------------------------------------------------------------------------------
def test_levels():
    assert (policy.LEVELS["radio_on"], policy.LEVELS["radio_off"]) == (1, 2)
    assert (policy.LEVELS["screen_lock"], policy.LEVELS["power_off"], policy.LEVELS["power_cancel"]) == (1, 2, 1)


def test_lock_runs_at_once(pc):
    assert power.act("lock").ok and pc == [["lock"]]


def test_shutdown_needs_confirmation_and_waits_60_seconds(pc):
    pending = power.act("shutdown")
    assert pending.error_code == E_NEEDS_CONFIRM and not pc
    done = power.act("shutdown", ctx={"token": pending.data["token"]})
    assert done.ok and pc == [["shutdown", "/s", "/t", "60"]] and done.data["delay_seconds"] == 60


def test_cancel_and_nothing_to_cancel(pc, monkeypatch):
    assert power.act("cancel").ok and pc[-1] == ["shutdown", "/a"]
    monkeypatch.setattr(power, "_run", lambda cmd: False)
    assert "no scheduled shutdown" in power.act("cancel").message


def test_bad_power_op(pc):
    assert power.act("format").error_code == E_BAD_ARGUMENTS and not pc


def test_battery_reading(monkeypatch):
    import psutil
    from collections import namedtuple
    B = namedtuple("B", "percent secsleft power_plugged")
    monkeypatch.setattr(psutil, "sensors_battery", lambda: B(76.4, 5400, False))
    assert power.battery().data == {"present": True, "percent": 76, "plugged": False, "minutes_left": 90}
    monkeypatch.setattr(psutil, "sensors_battery", lambda: None)
    assert power.battery().data == {"present": False}


# ---- understanding and chat ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,intent,slots", [
    ("turn off the wifi", "radio_control", {"radio": "wifi", "on": False}),
    ("bluetooth chalu karo", "radio_control", {"radio": "bluetooth", "on": True}),
    ("वाईफाई बंद करो", "radio_control", {"radio": "wifi", "on": False}),
    ("shutdown the pc right now", "power_action", {"op": "shutdown"}),
    ("laptop band kar do", "power_action", {"op": "shutdown"}),
    ("restart karo", "power_action", {"op": "restart"}),
    ("कंप्यूटर रीस्टार्ट करो", "power_action", {"op": "restart"}),
    ("lock the screen", "power_action", {"op": "lock"}),
    ("laptop ko sleep mode me dalo", "power_action", {"op": "sleep"}),
    ("cancel the shutdown", "power_action", {"op": "cancel"}),
])
def test_requests_become_frames(text, intent, slots):
    frame = frames.command(text)
    assert frame is not None and frame.intent == intent and frame.slots() == slots, (text, frames.parse(text))


@pytest.mark.parametrize("text", ["tips to sleep better", "lock the door", "restart notepad", "system status",
                                  "what is on my screen", "take a screenshot"])
def test_unrelated_requests_are_left_alone(text):
    frame = frames.command(text)
    assert frame is None or frame.intent not in ("radio_control", "power_action")


def test_chat_shutdown_asks_then_schedules(pc):
    cid = context.new_conversation()
    r = engine.handle_message("shut down the laptop", cid).data
    assert r["intent"] == "power_action" and r["confirmation"] and "shut down the PC in 60 seconds" in r["reply"] and not pc
    r = engine.confirm(cid, True).data
    assert "will shut down in 60 seconds" in r["reply"] and pc == [["shutdown", "/s", "/t", "60"]]


def test_chat_wifi_off_can_be_cancelled(radios):
    cid = context.new_conversation()
    assert engine.handle_message("wifi band karo", cid).data["confirmation"]
    engine.confirm(cid, False)
    assert radios["WiFi"] == "On"


def test_chat_lock_and_bluetooth_on(pc, radios):
    cid = context.new_conversation()
    assert engine.handle_message("lock karo", cid).data["reply"] == "Locked the PC."
    assert engine.handle_message("turn on bluetooth", cid).data["reply"] == "Bluetooth is on."


def test_negated_power_request_runs_nothing(pc):
    r = engine.handle_message("don't shut down the computer", context.new_conversation()).data
    assert r["intent"] == "negated" and not pc


def test_status_reply_includes_the_battery(monkeypatch):
    fresh_env()
    from adhyaksh.result import Result
    monkeypatch.setattr(engine.system, "status", lambda **k: Result.success({"cpu": 10.0, "ram": 20.0, "disk": 30.0}))
    monkeypatch.setattr(engine.power, "battery", lambda: Result.success({"present": True, "percent": 64, "plugged": True}))
    r = engine.handle_message("show cpu usage", context.new_conversation()).data  # a rule phrase: no trained model here
    assert r["reply"].startswith("CPU 10 percent") and "Battery 64 percent, plugged in." in r["reply"]

"""Phase 2b-1: speaker and microphone volume, screen brightness. The Windows audio endpoint and PowerShell are faked:
tests never change the real volume or brightness."""
import pytest

from adhyaksh.chat import context, engine
from adhyaksh.nlu import frames
from adhyaksh.result import E_BAD_ARGUMENTS, E_UNVERIFIED
from adhyaksh.safety import policy
from adhyaksh.tools import audio, display
from tests.helpers import fresh_env


class _Endpoint:
    def __init__(self, level=0.5, muted=0, sticky=False):
        self.level, self.muted, self.sticky = level, muted, sticky

    def GetMasterVolumeLevelScalar(self):
        return self.level

    def SetMasterVolumeLevelScalar(self, v, _ctx):
        if not self.sticky:
            self.level = v

    def GetMute(self):
        return self.muted

    def SetMute(self, m, _ctx):
        if not self.sticky:
            self.muted = m


@pytest.fixture
def speakers(monkeypatch):
    fresh_env()
    eps = {"speaker": _Endpoint(0.5), "mic": _Endpoint(0.3)}
    monkeypatch.setattr(audio, "_endpoint", lambda device: eps[device])
    monkeypatch.setattr(audio, "_unavailable", lambda: None)
    monkeypatch.setattr(audio, "_co_initialize", lambda: True)  # no real COM in tests
    monkeypatch.setattr(audio, "_co_uninitialize", lambda: None)
    return eps


def test_volume_works_repeatedly_from_different_threads(monkeypatch):
    """Real-test bug: the first volume command worked, every later one failed with OSError, because Streamlit runs each
    request on another thread and COM was not initialised there. Each call must start COM in its own thread and build
    a fresh endpoint."""
    import threading
    fresh_env()
    com = threading.local()
    log = {"init": 0, "uninit": 0, "built": 0}
    level = {"v": 0.5}

    def fake_init():
        com.on = True
        log["init"] += 1
        return True

    def fake_uninit():
        com.on = False
        log["uninit"] += 1

    def fake_endpoint(device):
        if not getattr(com, "on", False):
            raise OSError("[WinError -2147221008] CoInitialize has not been called")
        log["built"] += 1
        ep = _Endpoint(level["v"])
        orig = ep.SetMasterVolumeLevelScalar
        ep.SetMasterVolumeLevelScalar = lambda v, c: (orig(v, c), level.update(v=v))
        return ep
    monkeypatch.setattr(audio, "_co_initialize", fake_init)
    monkeypatch.setattr(audio, "_co_uninitialize", fake_uninit)
    monkeypatch.setattr(audio, "_endpoint", fake_endpoint)
    monkeypatch.setattr(audio, "_unavailable", lambda: None)
    results = []
    for value in (20, 40, 60):  # three commands, each on its own new thread, like three Streamlit reruns
        t = threading.Thread(target=lambda v=value: results.append(audio.control("set", "speaker", v)))
        t.start()
        t.join()
    assert [r.ok for r in results] == [True, True, True], [r.message for r in results]
    assert [r.data["level"] for r in results] == [20, 40, 60] and all(r.data["verified"] for r in results)
    assert log["init"] == log["uninit"] and log["init"] >= 3 and log["built"] >= 3  # balanced, fresh each time


def test_com_is_stopped_even_when_the_device_fails(monkeypatch):
    fresh_env()
    log = []
    monkeypatch.setattr(audio, "_co_initialize", lambda: log.append("init") or True)
    monkeypatch.setattr(audio, "_co_uninitialize", lambda: log.append("uninit"))
    monkeypatch.setattr(audio, "_unavailable", lambda: None)
    monkeypatch.setattr(audio, "_endpoint", lambda d: (_ for _ in ()).throw(OSError("no audio device")))
    res = audio.read("speaker")
    assert not res.ok and "could not be read" in res.message and log == ["init", "uninit"]
    log.clear()
    monkeypatch.setattr(audio, "_co_initialize", lambda: log.append("init") or False)  # thread already runs COM
    audio.read("speaker")
    assert log == ["init"]  # not ours to stop


@pytest.fixture
def screen(monkeypatch):
    fresh_env()
    state = {"level": 60, "calls": []}

    def fake_ps(script, timeout=15.0):
        state["calls"].append(script)
        if "WmiSetBrightness" in script:
            state["level"] = int(script.split("Brightness=[byte]")[1].split("}")[0])
            return True, "ok"
        return True, str(state["level"])
    monkeypatch.setattr(display, "powershell", fake_ps)
    monkeypatch.setattr(display.os, "name", "nt")
    return state


# ---- volume -------------------------------------------------------------------------------------------------
def test_set_step_mute_and_read_back(speakers):
    assert audio.control("set", "speaker", 35).data["level"] == 35 and speakers["speaker"].level == 0.35
    up = audio.control("up", "speaker")
    assert up.data["level"] == 45 and up.data["verified"] is True
    assert audio.control("down", "speaker", 50).data["level"] == 0  # clamped at 0
    assert audio.control("mute", "mic").data["muted"] and speakers["mic"].muted == 1
    assert audio.control("unmute", "mic").ok and speakers["mic"].muted == 0
    assert audio.read("speaker").data == {"device": "speaker", "level": 0, "muted": False}


def test_turning_up_also_unmutes(speakers):
    speakers["speaker"].muted = 1
    assert audio.control("up", "speaker").data["muted"] is False


def test_a_change_that_did_not_happen_is_reported(speakers):
    speakers["speaker"].sticky = True  # the driver ignores the change
    res = audio.control("set", "speaker", 80)
    assert res.error_code == E_UNVERIFIED and "50 percent, not 80" in res.message


def test_bad_volume_arguments():
    assert audio.control("set", "speaker").error_code == E_BAD_ARGUMENTS
    assert audio.control("set", "speaker", 140).error_code == E_BAD_ARGUMENTS
    assert audio.control("louder", "speaker").error_code == E_BAD_ARGUMENTS
    assert audio.read("headphones").error_code == E_BAD_ARGUMENTS


def test_volume_is_level_1_and_audited(speakers):
    from adhyaksh.safety import audit
    assert policy.LEVELS["volume_control"] == 1 and policy.LEVELS["brightness_control"] == 1
    audio.control("set", "speaker", 20)
    assert audit.list_recent(1)[0]["action"] == "volume_control"


# ---- brightness ------------------------------------------------------------------------------------------------
def test_brightness_set_and_steps(screen):
    assert display.control("set", 80).data == {"op": "set", "level": 80, "previous": 60, "verified": True}
    assert display.control("down").data["level"] == 70 and screen["level"] == 70
    assert display.control("up", 50).data["level"] == 100


def test_brightness_script_only_ever_gets_a_number(screen):
    display.control("set", 25)
    assert "Brightness=[byte]25}" in screen["calls"][-2] or "Brightness=[byte]25}" in "".join(screen["calls"])
    before = len(screen["calls"])
    for bad in ("25; Remove-Item C:/", -5, 101, True, 2.5):
        assert display.control("set", bad).error_code == E_BAD_ARGUMENTS  # refused before PowerShell runs
        assert audio.control("set", "speaker", bad).error_code == E_BAD_ARGUMENTS
    assert len(screen["calls"]) == before


def test_screen_without_brightness_support(monkeypatch):
    fresh_env()
    monkeypatch.setattr(display.os, "name", "nt")
    monkeypatch.setattr(display, "powershell", lambda s, timeout=15.0: (False, "not supported"))
    res = display.control("up")
    assert not res.ok and "external monitor" in res.message


# ---- understanding and chat -------------------------------------------------------------------------------------
@pytest.mark.parametrize("text,slots", [
    ("turn up the volume", {"device": "speaker", "op": "up", "level": None}),
    ("set volume to 40", {"device": "speaker", "op": "set", "level": 40}),
    ("volume 40%", {"device": "speaker", "op": "set", "level": 40}),
    ("आवाज़ ४० करो", {"device": "speaker", "op": "set", "level": 40}),
    ("awaaz band karo", {"device": "speaker", "op": "mute", "level": None}),
    ("awaaz wapas chalu karo", {"device": "speaker", "op": "unmute", "level": None}),
    ("mute", {"device": "speaker", "op": "mute", "level": None}),
    ("mic mute kari do", {"device": "mic", "op": "mute", "level": None}),
    ("વોલ્યુમ વધારો", {"device": "speaker", "op": "up", "level": None}),
    ("brightness 70", {"op": "set", "level": 70}),
    ("ब्राइटनेस कम करो", {"op": "down", "level": None}),
    ("બ્રાઇટનેસ ઓછી કરો", {"op": "down", "level": None}),
])
def test_requests_become_level_frames(text, slots):
    frame = frames.command(text)
    assert frame is not None and frame.slots() == slots, (text, frames.parse(text))


@pytest.mark.parametrize("text", ["don't mute the sound", "volume mat badhao", "બ્રાઇટનેસ ઓછી ના કરો"])
def test_negated_level_requests(text):
    assert frames.negated_command(text) is not None


@pytest.mark.parametrize("text", ["आवाज़ की भाषा हिंदी करो", "open sound settings", "chup ho jao", "tips to sleep better"])
def test_unrelated_requests_are_not_level_commands(text):
    frame = frames.command(text)
    assert frame is None or frame.intent not in ("volume_control", "brightness_control")


def test_chat_round_trip(speakers, screen):
    cid = context.new_conversation()
    assert engine.handle_message("set the volume to 35 percent", cid).data["reply"] == "The volume is at 35 percent."
    assert engine.handle_message("mic mute karo", cid).data["reply"] == "The microphone is muted."
    assert engine.handle_message("brightness 80 pe rakho", cid).data["reply"] == "Brightness is at 80 percent."
    assert engine.handle_message("आवाज़ कम करो", cid).data["reply"].endswith("25 प्रतिशत है।")


def test_chat_mode_does_not_change_the_system(speakers):
    r = engine.handle_message("set the volume to 10", context.new_conversation(), mode="chat").data
    assert speakers["speaker"].level == 0.5 and r["intent"] == "volume_control"

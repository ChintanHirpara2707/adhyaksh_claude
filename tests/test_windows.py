"""Phase 2b-3: window management. user32 and the window list are faked: tests never move or close a real window."""
import pytest

from adhyaksh.chat import context, engine
from adhyaksh.nlu import frames
from adhyaksh.result import E_BAD_ARGUMENTS, E_FILE_NOT_FOUND, E_UNVERIFIED
from adhyaksh.safety import policy
from adhyaksh.tools import windows
from tests.helpers import fresh_env


class _User32:
    def __init__(self, ignore=False):
        self.state = {101: {"min": False, "max": False}, 202: {"min": False, "max": False}, 303: {"min": False, "max": False}}
        self.fg, self.calls, self.ignore = 0, [], ignore

    def ShowWindow(self, h, sw):
        self.calls.append(("show", h, sw))
        if not self.ignore:
            self.state[h].update(min=sw == 6, max=sw == 3)

    def IsIconic(self, h):
        return self.state[h]["min"]

    def IsZoomed(self, h):
        return self.state[h]["max"]

    def IsWindow(self, h):
        return h in self.state

    def GetForegroundWindow(self):
        return self.fg

    def SetForegroundWindow(self, h):
        self.fg = h

    def keybd_event(self, *a):
        pass

    def PostMessageW(self, h, msg, *a):
        self.calls.append(("post", h, msg))
        self.state.pop(h, None)


WINDOWS = [{"hwnd": 101, "title": "Inbox - Google Chrome", "pid": 11, "process": "chrome.exe"},
           {"hwnd": 202, "title": "notes.txt - Notepad", "pid": 22, "process": "notepad.exe"},
           {"hwnd": 303, "title": "Calculator", "pid": 33, "process": "ApplicationFrameHost.exe"}]


@pytest.fixture
def desk(monkeypatch):
    fresh_env()
    u = _User32()
    monkeypatch.setattr(windows, "_user32", lambda: u)
    monkeypatch.setattr(windows, "_enum", lambda: [w for w in WINDOWS if w["hwnd"] in u.state])
    monkeypatch.setattr(windows.os, "name", "nt")
    monkeypatch.setattr(windows.time, "sleep", lambda s: None)
    return u


def test_hidden_tool_shell_and_duplicate_windows_are_not_listed(monkeypatch):
    """Real-test bug: the count and list included background windows (Cortana, Settings, Calculator duplicates)."""
    fresh_env()
    raw = [
        {"hwnd": 1, "title": "Inbox - Google Chrome", "pid": 11, "process": "chrome.exe", "cloaked": False, "tool": False},
        {"hwnd": 2, "title": "Cortana", "pid": 12, "process": "Cortana.exe", "cloaked": True, "tool": False},
        {"hwnd": 3, "title": "Settings", "pid": 13, "process": "ApplicationFrameHost.exe", "cloaked": True, "tool": False},
        {"hwnd": 4, "title": "Calculator", "pid": 14, "process": "ApplicationFrameHost.exe", "cloaked": False, "tool": False},
        {"hwnd": 5, "title": "Calculator", "pid": 15, "process": "CalculatorApp.exe", "cloaked": False, "tool": False},
        {"hwnd": 6, "title": "Calculator", "pid": 16, "process": "ApplicationFrameHost.exe", "cloaked": True, "tool": False},
        {"hwnd": 7, "title": "Color picker", "pid": 17, "process": "paint.exe", "cloaked": False, "tool": True},
        {"hwnd": 8, "title": "Program Manager", "pid": 18, "process": "explorer.exe", "cloaked": False, "tool": False},
        {"hwnd": 9, "title": "notes.txt  -  Notepad", "pid": 19, "process": "notepad.exe", "cloaked": False, "tool": False},
    ]
    monkeypatch.setattr(windows, "_raw_windows", lambda: raw)
    monkeypatch.setattr(windows.os, "name", "nt")
    shown = windows.list_windows().data["windows"]
    assert [w["title"] for w in shown] == ["Inbox - Google Chrome", "Calculator", "notes.txt - Notepad"]
    assert shown[1]["app"] == "ApplicationFrameHost.exe"  # the top-most Calculator frame is the one kept
    assert [w["hwnd"] for w in windows._enum()] == [1, 4, 9]


def test_find_by_app_store_app_and_title(desk):
    assert windows.find("chrome")["hwnd"] == 101
    assert windows.find("calculator")["hwnd"] == 303  # the ApplicationFrameHost frame of a Store app
    assert windows.find("notes.txt")["hwnd"] == 202  # title words
    assert windows.find("photoshop") is None


def test_minimize_maximize_restore_are_verified(desk):
    res = windows.control("minimize", "chrome")
    assert res.ok and res.data["verified"] is True and desk.state[101]["min"]
    assert windows.control("restore", "chrome").ok and not desk.state[101]["min"]
    assert windows.control("maximize", "notepad").data["verified"] is True


def test_a_window_that_ignores_the_request_is_reported(desk):
    desk.ignore = True
    assert windows.control("minimize", "chrome").error_code == E_UNVERIFIED


def test_focus_and_polite_close(desk):
    assert windows.control("focus", "notepad").ok and desk.fg == 202
    res = windows.control("close", "calculator")
    assert res.ok and ("post", 303, 0x0010) in desk.calls and res.data["verified"] is True


def test_bad_or_missing_targets(desk):
    assert windows.control("explode", "chrome").error_code == E_BAD_ARGUMENTS
    assert windows.control("minimize", "").error_code == E_BAD_ARGUMENTS
    assert windows.control("minimize", "photoshop").error_code == E_FILE_NOT_FOUND


def test_level_and_minimize_all(desk, monkeypatch):
    assert policy.LEVELS["window_control"] == 1
    scripts = []
    monkeypatch.setattr("adhyaksh.tools.display.powershell", lambda s, timeout=15.0: scripts.append(s) or (True, ""))
    assert windows.control("minimize_all").ok and scripts == ["(New-Object -ComObject Shell.Application).MinimizeAll()"]


@pytest.mark.parametrize("text,slots", [
    ("minimize chrome", {"op": "minimize", "target": "chrome"}),
    ("maximize the notepad window", {"op": "maximize", "target": "notepad"}),
    ("switch to calculator", {"op": "focus", "target": "calculator"}),
    ("chrome pe jao", {"op": "focus", "target": "chrome"}),
    ("नोटपैड बड़ा करो", {"op": "maximize", "target": "notepad"}),
    ("ક્રોમ નાનું કરો", {"op": "minimize", "target": "chrome"}),
    ("minimize all windows", {"op": "minimize_all", "target": ""}),
    ("सारी विंडो छोटी करो", {"op": "minimize_all", "target": ""}),
    ("બધી વિન્ડો નાની કરો", {"op": "minimize_all", "target": ""}),
])
def test_requests_become_window_frames(text, slots):
    frame = frames.command(text)
    assert frame is not None and frame.intent == "window_control" and frame.slots() == slots, (text, frames.parse(text))


@pytest.mark.parametrize("text", ["close this window", "update windows now", "go to github.com", "volume bada karo"])
def test_not_window_commands(text):
    frame = frames.command(text)
    assert frame is None or frame.intent != "window_control"


def test_chat_round_trip(desk):
    cid = context.new_conversation()
    assert engine.handle_message("minimize chrome", cid).data["reply"] == "Minimized Inbox - Google Chrome."
    assert engine.handle_message("notepad pe jao", cid).data["reply"] == "Switched to notes.txt - Notepad."
    r = engine.handle_message("switch to paint", cid).data  # a known app with no open window
    assert "No open window matches paint" in r["reply"]

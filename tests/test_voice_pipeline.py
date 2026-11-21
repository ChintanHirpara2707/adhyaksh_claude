"""Phase 3b: native voice. The microphone, speech-to-text, the Windows voice and the assistant are faked: tests never
record, transcribe or speak. Covered: speech detection, wake word in one phrase or two, ignoring speech not meant
for the assistant, push-to-talk, answering a confirmation without the wake word, barge-in, and the start checks."""
import threading

import numpy as np
import pytest

from adhyaksh import config, events
from adhyaksh.result import Result
from adhyaksh.voice import pipeline
from tests.helpers import fresh_env


@pytest.fixture(autouse=True)
def _env():
    fresh_env()
    events.reset()
    yield
    events.reset()


class FakeSpeaker:
    def __init__(self):
        self.said, self.stopped = [], 0
        self.speaking = threading.Event()

    def speak(self, text, lang="en"):
        self.said.append((text, lang))

    def stop(self):
        self.stopped += 1
        self.speaking.clear()


@pytest.fixture(autouse=True)
def _replies_spoken(monkeypatch):
    """'Reply with voice' on (no real setting is read or changed); a test can switch it off."""
    from adhyaksh import config
    real = config.get_bool
    state = {"voice_reply": True}
    monkeypatch.setattr(config, "get_bool", lambda key: state[key] if key in state else real(key))
    return state


def _pipe(heard, replies=None):
    """A pipeline whose recogniser 'hears' the given texts in order and whose assistant answers from replies."""
    texts = iter(heard)
    asked = []

    def handle(cmd):
        asked.append(cmd)
        return (replies or {}).get(cmd, {"reply": f"Done: {cmd}.", "intent": "x"})
    p = pipeline.VoicePipeline(transcribe=lambda wav: Result.success({"text": next(texts)}), handle=handle,
                               speaker=FakeSpeaker(), words=["adhyaksh", "hey assistant"], lang="en-IN")
    return p, asked


SPEECH = np.zeros(pipeline.RATE, dtype="int16")


# ---- speech detection ------------------------------------------------------------------------------------------------
def test_segmenter_cuts_one_utterance_out_of_noise():
    seg = pipeline.Segmenter(min_rms=300)
    rng = np.random.default_rng(0)
    quiet = [rng.normal(0, 40, pipeline.FRAME).astype("int16") for _ in range(30)]
    loud = [rng.normal(0, 4000, pipeline.FRAME).astype("int16") for _ in range(20)]
    out = [seg.feed(f) for f in quiet + loud + quiet]
    done = [o for o in out if o is not None]
    assert len(done) == 1 and len(done[0]) >= 20 * pipeline.FRAME and not seg.active


def test_wav_round_trip():
    import io
    import wave
    with wave.open(io.BytesIO(pipeline.to_wav(SPEECH)), "rb") as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth(), w.getnframes()) == (16000, 1, 2, 16000)


# ---- wake word, command window, push-to-talk -------------------------------------------------------------------------------
def test_wake_word_and_command_in_one_phrase():
    p, asked = _pipe(["Adhyaksh, open notepad"])
    assert p.on_utterance(SPEECH) == "open notepad" and asked == ["open notepad"]
    assert p.speaker.said == [("Done: open notepad.", "en")]


def test_with_reply_with_voice_off_the_command_runs_but_nothing_is_spoken(_replies_spoken):
    _replies_spoken["voice_reply"] = False
    p, asked = _pipe(["Adhyaksh, open notepad"])
    assert p.on_utterance(SPEECH) == "open notepad" and asked == ["open notepad"] and p.speaker.said == []


def test_speech_not_meant_for_the_assistant_is_ignored():
    p, asked = _pipe(["so I told him to open notepad"])
    assert p.on_utterance(SPEECH) is None and asked == [] and p.speaker.said == []


def test_wake_word_alone_then_the_command():
    p, asked = _pipe(["Adhyaksh", "volume 30"])
    assert p.on_utterance(SPEECH) is None and events.current_state()["state"] == "listening"
    assert p.on_utterance(SPEECH) == "volume 30" and asked == ["volume 30"]


def test_the_command_window_closes():
    p, asked = _pipe(["Adhyaksh", "volume 30"])
    p.on_utterance(SPEECH)
    p.open_until = 0.0  # the window ran out
    assert p.on_utterance(SPEECH) is None and asked == []


def test_push_to_talk_needs_no_wake_word():
    p, asked = _pipe(["what time is it"])
    p.listen_now()
    assert p.on_utterance(SPEECH) == "what time is it"


def test_a_confirmation_can_be_answered_without_the_wake_word():
    p, asked = _pipe(["Adhyaksh delete notes.txt", "yes"],
                     replies={"delete notes.txt": {"reply": "Delete notes.txt? Confirm or cancel.", "confirmation": {"token": "t"}},
                              "yes": {"reply": "Moved to the Recycle Bin: notes.txt.", "intent": "confirmation"}})
    p.on_utterance(SPEECH)
    assert "Say yes to confirm, or no to cancel." in p.speaker.said[0][0]
    assert p.on_utterance(SPEECH) == "yes" and asked == ["delete notes.txt", "yes"]
    assert p.open_until == 0.0  # the window closes again after the answer


def test_a_failed_recognition_does_nothing():
    p = pipeline.VoicePipeline(transcribe=lambda wav: Result.failure("E_ACTION_FAILED", "no speech"),
                               handle=lambda c: pytest.fail("must not run"), speaker=FakeSpeaker(), words=["adhyaksh"])
    assert p.on_utterance(SPEECH) is None


# ---- barge-in ---------------------------------------------------------------------------------------------------------------
def test_talking_over_the_assistant_stops_it():
    p, _ = _pipe([])
    p.speaker.speaking.set()
    p.on_speech_start()
    assert p.speaker.stopped == 1
    config.set_value("voice_barge_in", False)
    p.speaker.speaking.set()
    p.on_speech_start()
    assert p.speaker.stopped == 1


# ---- starting ---------------------------------------------------------------------------------------------------------------
def test_never_starts_without_the_local_speech_model(monkeypatch):
    from adhyaksh.voice import stt
    monkeypatch.setattr(stt, "available", lambda: False)
    ok, why = pipeline.start()
    assert not ok and "local speech model" in why and not pipeline.status()["running"]


def test_voice_is_off_by_default_and_the_listen_endpoint_says_so():
    from starlette.testclient import TestClient

    from adhyaksh import server
    assert config.get_bool("voice_engine") is False
    c = TestClient(server.create_app(), base_url="http://127.0.0.1:8765")
    r = c.post("/v1/voice/listen", headers={server.HEADER: server.token()})
    assert r.status_code == 409 and "not running" in r.json()["error"]
    assert c.get("/v1/voice", headers={server.HEADER: server.token()}).json()["running"] is False


# ---- the Windows voice (SAPI faked) ---------------------------------------------------------------------------------------
class _FakeVoices:
    def __init__(self, langs):
        self.items = [type("V", (), {"lang": l, "GetAttribute": lambda s, k, l=l: l})() for l in langs]
        self.Count = len(self.items)

    def Item(self, i):
        return self.items[i]


class _FakeSapi:
    def __init__(self, langs=("409", "439")):
        self.spoken, self.Voice, self.Rate, self.voices = [], None, 0, _FakeVoices(langs)
        self.long = False

    def GetVoices(self):
        return self.voices

    def Speak(self, text, flags):
        self.spoken.append((text, flags))

    def WaitUntilDone(self, ms):
        import time as _t
        _t.sleep(ms / 1000)
        return not self.long


def test_speaker_speaks_in_its_own_com_thread_and_picks_the_language(monkeypatch):
    import comtypes
    import comtypes.client
    sapi, log = _FakeSapi(), []
    monkeypatch.setattr(comtypes, "CoInitialize", lambda: log.append("init"))
    monkeypatch.setattr(comtypes, "CoUninitialize", lambda: log.append("uninit"))
    monkeypatch.setattr(comtypes.client, "CreateObject", lambda name: sapi)
    s = pipeline.Speaker()
    s.speak("नमस्ते", "hi")
    s.close()
    s._thread.join(timeout=5)
    assert sapi.spoken == [("नमस्ते", 3)] and sapi.Voice.lang == "439" and log == ["init", "uninit"]


def test_speaker_stop_cuts_a_long_sentence(monkeypatch):
    import comtypes
    import comtypes.client
    sapi = _FakeSapi()
    sapi.long = True  # never finishes on its own
    monkeypatch.setattr(comtypes, "CoInitialize", lambda: None)
    monkeypatch.setattr(comtypes, "CoUninitialize", lambda: None)
    monkeypatch.setattr(comtypes.client, "CreateObject", lambda name: sapi)
    s = pipeline.Speaker()
    s.speak("a very long answer", "en")
    assert s.speaking.wait(timeout=5)
    s.stop()
    s.close()
    s._thread.join(timeout=5)
    assert sapi.spoken[-1] == ("", 3) and not s.speaking.is_set()

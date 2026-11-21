"""Native voice for the background engine: microphone -> speech detection -> local speech-to-text -> wake word ->
the assistant -> spoken reply, without a browser tab.

* Microphone: sounddevice (16 kHz mono). Speech detection: an energy detector that adapts to the room's noise.
* Speech-to-text: the local faster-whisper model only (adhyaksh/voice/stt.py). Audio never leaves the PC; without
  the local model the pipeline does not start (it never falls back to an online recogniser).
* Wake word: the user's wake words ("adhyaksh", ...) at the start of a phrase, matched in the local transcript. A
  wake word alone opens a short window for the command. Push-to-talk (the HUD hotkey) needs no wake word, and
  neither does the answer to a question the assistant just asked ("Confirm?" -> "yes").
* Voice: the Windows voices (SAPI through comtypes, no extra package), chosen by the reply's language when such a
  voice is installed. Barge-in: speaking stops as soon as the user starts talking.
* Every command goes through engine.handle_message, so the safety gateway applies exactly as when typing.
Off by default (setting `voice_engine`): an always-listening microphone is the user's choice.
"""
from __future__ import annotations

import io
import logging
import queue
import threading
import time
import wave

from adhyaksh import config, events, logging_setup

RATE = 16000
FRAME = 480  # 30 ms
COMMAND_WINDOW_S = 8.0  # after a bare wake word, or a question from the assistant
_LANG_LCID = {"en": ("4009", "409", "809"), "hi": ("439",), "gu": ("447",)}  # SAPI language attribute values (hex)


# ---- speech detection ------------------------------------------------------------------------------------------------
class Segmenter:
    """Cuts a stream of 30 ms frames into utterances with an adaptive energy threshold."""

    def __init__(self, min_rms: float = 300.0, start_frames: int = 3, end_silence_s: float = 0.8, max_s: float = 15.0):
        self.min_rms, self.start_frames = min_rms, start_frames
        self.end_frames = int(end_silence_s * 1000 / 30)
        self.max_frames = int(max_s * 1000 / 30)
        self.floor = min_rms / 3
        self.loud, self.quiet, self.buf, self.active = 0, 0, [], False

    @staticmethod
    def rms(frame) -> float:
        import numpy as np
        f = np.asarray(frame, dtype="float32")
        return float(np.sqrt(np.mean(f * f))) if f.size else 0.0

    def is_speech(self, frame) -> bool:
        return self.rms(frame) > max(self.min_rms, self.floor * 3)

    def feed(self, frame):
        """Returns the int16 samples of a finished utterance, else None."""
        import numpy as np
        loud = self.is_speech(frame)
        if not self.active:
            if not loud:
                self.floor = 0.95 * self.floor + 0.05 * self.rms(frame)  # learn the room's noise between phrases
            self.loud = self.loud + 1 if loud else 0
            self.buf = (self.buf + [frame])[-self.start_frames - 5:]  # keep a little audio from just before the start
            if self.loud >= self.start_frames:
                self.active, self.quiet = True, 0
            return None
        self.buf.append(frame)
        self.quiet = 0 if loud else self.quiet + 1
        if self.quiet >= self.end_frames or len(self.buf) >= self.max_frames:
            out = np.concatenate([np.asarray(f, dtype="int16") for f in self.buf])
            self.active, self.loud, self.quiet, self.buf = False, 0, 0, []
            return out
        return None


def to_wav(samples) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(samples.astype("<i2").tobytes())
    return buf.getvalue()


# ---- the Windows voice ----------------------------------------------------------------------------------------------------
class Speaker:
    """SAPI voice in its own thread (COM objects belong to the thread that made them). speak() returns at once;
    stop() interrupts mid-sentence."""

    def __init__(self):
        self._q: queue.Queue = queue.Queue()
        self._stop = threading.Event()
        self.speaking = threading.Event()
        self._thread = threading.Thread(target=self._run, name="adhyaksh-tts", daemon=True)
        self._thread.start()

    def speak(self, text: str, lang: str = "en") -> None:
        if text.strip():
            self._stop.clear()
            self._q.put((text, lang))

    def stop(self) -> None:
        self._stop.set()

    def close(self) -> None:
        self._q.put(None)

    def _pick_voice(self, voice, lang: str):
        voices = voice.GetVoices()
        for i in range(voices.Count):
            item = voices.Item(i)
            if item.GetAttribute("Language").split(";")[0].casefold() in _LANG_LCID.get(lang, ()):
                return item
        return None

    def _run(self) -> None:
        import comtypes
        import comtypes.client
        comtypes.CoInitialize()
        try:
            voice = comtypes.client.CreateObject("SAPI.SpVoice")
            voice.Rate = max(-10, min(10, round((float(config.get("tts_rate")) - 1.0) * 10)))
            while True:
                job = self._q.get()
                if job is None:
                    break
                text, lang = job
                chosen = self._pick_voice(voice, lang)
                if chosen is not None:
                    voice.Voice = chosen
                self.speaking.set()
                events.set_state("speaking")
                voice.Speak(text, 1 | 2)  # asynchronous, purge anything still queued
                while not voice.WaitUntilDone(100):
                    if self._stop.is_set():
                        voice.Speak("", 1 | 2)  # barge-in: cut the sentence off
                        break
                self.speaking.clear()
                events.set_state("idle")
            del voice
        except Exception as exc:  # no audio output device, SAPI missing
            logging_setup.event("tts_error", logging.WARNING, error=type(exc).__name__)
        finally:
            import gc
            gc.collect()
            comtypes.CoUninitialize()


# ---- the pipeline -----------------------------------------------------------------------------------------------------------
class VoicePipeline:
    """Wake word, command window, push-to-talk and barge-in around injectable parts (tests use fakes)."""

    def __init__(self, transcribe=None, handle=None, speaker=None, words=None, lang: str | None = None):
        from adhyaksh.voice import speech
        self.lang = lang or config.get("voice_lang")
        self.transcribe = transcribe or (lambda wav: _transcribe(wav, self.lang))
        self.handle = handle or _handle
        self.speaker = speaker
        self.words = words if words is not None else speech.wake_words(config.get("wake_words"))
        self.open_until = 0.0  # a command may come without the wake word until this time
        self.heard: list[str] = []

    def listen_now(self) -> None:
        """Push-to-talk: the next phrase is a command, no wake word needed."""
        self.open_until = time.monotonic() + COMMAND_WINDOW_S
        events.set_state("listening")

    def on_speech_start(self) -> None:
        """The user started talking: stop speaking (barge-in)."""
        if self.speaker is not None and self.speaker.speaking.is_set() and config.get_bool("voice_barge_in"):
            self.speaker.stop()

    def on_utterance(self, samples) -> str | None:
        """One finished phrase. Returns the command that was run, or None."""
        from adhyaksh.voice import bridge, speech
        res = self.transcribe(to_wav(samples))
        if not res.ok:
            return None
        text = speech.clean_transcript(res.data["text"])
        self.heard.append(text)
        now = time.monotonic()
        matched, rest = speech.strip_wake(text, self.words)
        if matched and not rest:
            self.listen_now()  # "Adhyaksh" ... then the command
            return None
        if not matched and now > self.open_until:
            return None  # not for us
        command = rest if matched else text
        self.open_until = 0.0
        reply = self.handle(command)
        if reply.get("confirmation") or (reply.get("intent") in ("agent_ask",) or reply.get("action") == "clarify"):
            self.open_until = time.monotonic() + COMMAND_WINDOW_S  # the answer to a question needs no wake word
        from adhyaksh import config
        # Spoken only with "Reply with voice" on (Settings); off, the reply is text only (console, HUD caption).
        if self.speaker is not None and reply.get("reply") and config.get_bool("voice_reply"):
            spoken = bridge.speakable(reply["reply"])
            if reply.get("confirmation"):
                spoken += " " + speech.confirm_prompt(self.lang)
            self.speaker.speak(spoken, self.lang[:2])
        return command


def _transcribe(wav: bytes, lang: str):
    from adhyaksh.voice import stt
    return stt.transcribe(wav, lang)


def _handle(text: str) -> dict:
    from adhyaksh import server
    from adhyaksh.chat import context, engine
    with server._ENGINE_LOCK:
        res = engine.handle_message(text, context.latest_conversation(), voice=True)
    return res.data if res.ok else {"reply": res.message}


# ---- running it in the engine ------------------------------------------------------------------------------------------------
_state = {"thread": None, "stop": threading.Event(), "pipeline": None, "error": ""}


def ready() -> tuple[bool, str]:
    """Can the native voice start? (local speech model present, microphone package installed)"""
    from adhyaksh.voice import stt
    if not stt.available():
        return False, "Native voice needs the local speech model (Settings, Voice, download) and faster-whisper."
    try:
        import sounddevice  # noqa: F401
    except ImportError:
        return False, "Native voice needs the sounddevice package: pip install sounddevice"
    return True, ""


def start() -> tuple[bool, str]:
    ok, why = ready()
    if not ok:
        _state["error"] = why
        return False, why
    if _state["thread"] and _state["thread"].is_alive():
        return True, ""
    _state["stop"].clear()
    pipe = VoicePipeline(speaker=Speaker())
    _state["pipeline"] = pipe

    def loop():
        import sounddevice as sd
        frames: queue.Queue = queue.Queue(maxsize=200)
        seg = Segmenter()
        with sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                            callback=lambda data, n, t, status: frames.put_nowait(data[:, 0].copy()) if not frames.full() else None):
            while not _state["stop"].is_set():
                try:
                    frame = frames.get(timeout=0.5)
                except queue.Empty:
                    continue
                was_active = seg.active
                utterance = seg.feed(frame)
                if seg.active and not was_active:
                    pipe.on_speech_start()
                if utterance is not None:
                    try:
                        pipe.on_utterance(utterance)
                    except Exception as exc:
                        logging_setup.event("voice_error", logging.WARNING, error=type(exc).__name__)
        pipe.speaker.close()

    _state["thread"] = threading.Thread(target=loop, name="adhyaksh-voice", daemon=True)
    _state["thread"].start()
    logging_setup.event("voice_start")
    return True, ""


def stop() -> None:
    _state["stop"].set()


def status() -> dict:
    t = _state["thread"]
    return {"running": bool(t and t.is_alive()), "error": _state["error"],
            "wake_words": (_state["pipeline"].words if _state["pipeline"] else [])}

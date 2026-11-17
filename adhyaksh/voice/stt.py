"""Local speech-to-text with faster-whisper (optional, offline, CPU).

The browser's speech recognition sends audio to an online service in Chrome. This module transcribes on the
laptop instead. It is used only when the faster-whisper package is installed AND the model files are already in
models/whisper: nothing is downloaded automatically, download() runs only from the Settings button.
"""
from __future__ import annotations

import io
import threading
import time
import wave

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED, Result

MAX_SECONDS = 30
MAX_BYTES = 4 * 1024 * 1024
SIZES = {"tiny": "about 75 MB, fastest, weakest", "base": "about 145 MB, good balance",
         "small": "about 480 MB, better for Hindi and Gujarati, slower"}
LANGS = {"en-IN": "en", "hi-IN": "hi", "gu-IN": "gu"}
_MODEL = {"size": None, "obj": None}
_LOCK = threading.Lock()


def model_size() -> str:
    size = config.get("stt_model")
    return size if size in SIZES else "base"


def download_root():
    d = config.models_dir() / "whisper"
    d.mkdir(parents=True, exist_ok=True)
    return d


def installed() -> bool:
    try:
        import faster_whisper  # noqa: F401
        return True
    except Exception:
        return False


def model_present(size: str | None = None) -> bool:
    key = f"faster-whisper-{size or model_size()}".lower()
    for p in download_root().glob("models--*"):
        if p.name.lower().endswith(key) and any(f.name == "model.bin" for f in p.rglob("model.bin")):
            return True
    return False


def available() -> bool:
    """True when local transcription can run now."""
    return config.get("stt_engine") == "local" and installed() and model_present()


def _load(local_only: bool = True):
    with _LOCK:
        if _MODEL["obj"] is None or _MODEL["size"] != model_size():
            from faster_whisper import WhisperModel
            _MODEL["obj"] = WhisperModel(model_size(), device="cpu", compute_type="int8",
                                         download_root=str(download_root()), local_files_only=local_only)
            _MODEL["size"] = model_size()
        return _MODEL["obj"]


def download() -> tuple[bool, str]:
    """Fetch the selected model into models/whisper. Called only on the user's request."""
    if not installed():
        return False, "The faster-whisper package is not installed. Run: pip install faster-whisper"
    try:
        _MODEL["obj"] = None
        _load(local_only=False)
        return True, f"Speech model '{model_size()}' is ready."
    except Exception as exc:  # network or disk problems
        return False, f"The speech model could not be downloaded ({type(exc).__name__}). Check the internet connection and free disk space."


def wav_to_float(data: bytes):
    """16-bit PCM WAV bytes (any rate, mono or stereo) to a 16 kHz mono float32 array."""
    import numpy as np

    with wave.open(io.BytesIO(data), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError("Only 16-bit PCM WAV audio is supported.")
        rate, channels, frames = w.getframerate(), w.getnchannels(), w.readframes(w.getnframes())
    audio = np.frombuffer(frames, dtype="<i2").astype("float32") / 32768.0
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != 16000 and len(audio):
        n = int(round(len(audio) * 16000 / rate))
        audio = np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype("float32")
    return audio


def transcribe(data: bytes, lang: str | None = None) -> Result:
    """Transcribe one utterance. lang: en-IN, hi-IN, gu-IN, a two-letter code, or None to detect.
    Returns {text, language, seconds, ms}."""
    if not installed():
        return Result.failure(E_ACTION_FAILED, "Local speech recognition needs the faster-whisper package (pip install faster-whisper).")
    if not model_present():
        return Result.failure(E_ACTION_FAILED, "The local speech model is not downloaded yet. Open Settings, Voice, to download it.")
    if not data or len(data) > MAX_BYTES:
        return Result.failure(E_ACTION_FAILED, "The recording is empty or too long.")
    try:
        audio = wav_to_float(data)
    except (wave.Error, ValueError, EOFError) as exc:
        return Result.failure(E_ACTION_FAILED, f"The recording could not be read ({exc}).")
    seconds = len(audio) / 16000
    if seconds < 0.3:
        return Result.failure(E_ACTION_FAILED, "The recording is too short.")
    audio = audio[: MAX_SECONDS * 16000]
    code = LANGS.get(lang or "", lang if lang in ("en", "hi", "gu") else None)
    t0 = time.perf_counter()
    try:
        segments, info = _load().transcribe(audio, language=code, beam_size=1, vad_filter=False,
                                            condition_on_previous_text=False)
        text = " ".join(s.text.strip() for s in segments).strip()
    except Exception as exc:  # broken model files or out of memory
        return Result.failure(E_ACTION_FAILED, f"Local speech recognition failed ({type(exc).__name__}).")
    if not text:
        return Result.failure(E_ACTION_FAILED, "No speech was recognised. Please try again.")
    return Result.success({"text": text, "language": info.language, "seconds": round(seconds, 2),
                           "ms": round((time.perf_counter() - t0) * 1000)})

"""Speaker and microphone volume (Windows Core Audio through pycaw). Every change goes through the safety gateway
(level 1: reversible) and is read back afterwards by the gateway's post-condition check.

Levels are percentages 0-100. A step without a number moves by STEP percent.
"""
from __future__ import annotations

import os

from adhyaksh.result import E_ACTION_FAILED, E_BAD_ARGUMENTS, E_UNSUPPORTED_OS, Result
from adhyaksh.safety import policy

STEP = 10
DEVICES = ("speaker", "mic")
OPS = ("set", "up", "down", "mute", "unmute")


def _ctx(ctx: dict | None) -> dict:
    ctx = ctx or {}
    return {"user_text": ctx.get("user_text", ""), "intent": ctx.get("intent", "")}


def _endpoint(device: str):
    """The IAudioEndpointVolume of the default speaker or microphone. Built fresh on every call: COM objects belong to
    the thread (and COM session) that created them, and Streamlit runs each request on a different thread."""
    from pycaw.pycaw import AudioUtilities
    if device == "mic":
        return AudioUtilities.CreateDevice(AudioUtilities.GetMicrophone()).EndpointVolume
    return AudioUtilities.GetSpeakers().EndpointVolume


def _co_initialize() -> bool:
    """Start COM in this thread. True when this call started it (and must stop it); False when the thread already runs
    COM in another mode, which is fine to use as it is."""
    import comtypes
    try:
        comtypes.CoInitialize()
        return True
    except OSError:
        return False


def _co_uninitialize() -> None:
    import comtypes
    comtypes.CoUninitialize()


def _with_endpoint(device: str, work):
    """Run work(endpoint) with COM initialised in the calling thread. Every COM reference is released before COM is
    stopped again (releasing one afterwards would crash), so nothing is cached between calls."""
    import gc
    started = _co_initialize()
    try:
        ep = _endpoint(device)
        try:
            return work(ep)
        finally:
            del ep
            gc.collect()  # drop the device wrappers pycaw created, while COM is still running
    finally:
        if started:
            _co_uninitialize()


def _unavailable() -> Result | None:
    if os.name != "nt":
        return Result.failure(E_UNSUPPORTED_OS, "Volume control works on Windows only.")
    try:
        import pycaw  # noqa: F401
    except ImportError:
        return Result.failure(E_ACTION_FAILED, "Volume control needs the pycaw package: pip install pycaw comtypes")
    return None


def read(device: str = "speaker") -> Result:
    """Current level (0-100) and mute state. Read-only: no gateway needed."""
    if device not in DEVICES:
        return Result.failure(E_BAD_ARGUMENTS, f"device must be one of: {', '.join(DEVICES)}.")
    bad = _unavailable()
    if bad:
        return bad
    try:
        return _with_endpoint(device, lambda ep: Result.success(
            {"device": device, "level": round(ep.GetMasterVolumeLevelScalar() * 100), "muted": bool(ep.GetMute())}))
    except Exception as exc:  # no audio device, driver error
        return Result.failure(E_ACTION_FAILED, f"The {device} could not be read ({type(exc).__name__}).")


def control(op: str, device: str = "speaker", level: int | None = None, *, ctx: dict | None = None) -> Result:
    """set (needs level), up / down (by level or STEP), mute, unmute."""
    if op not in OPS or device not in DEVICES:
        return Result.failure(E_BAD_ARGUMENTS, f"op must be one of {', '.join(OPS)} and device one of {', '.join(DEVICES)}.")
    if op == "set" and level is None:
        return Result.failure(E_BAD_ARGUMENTS, "Say the level to set, for example 40 percent.")
    from adhyaksh.tools.display import as_level
    level = as_level(level)
    if level is False:
        return Result.failure(E_BAD_ARGUMENTS, "The level must be a whole number between 0 and 100.")
    bad = _unavailable()
    if bad:
        return bad
    target = f"{device} {op}" + (f" {level}" if level is not None else "")

    def go() -> Result:
        return _with_endpoint(device, change)

    def change(ep) -> Result:
        now = round(ep.GetMasterVolumeLevelScalar() * 100)
        if op in ("mute", "unmute"):
            ep.SetMute(1 if op == "mute" else 0, None)
            return Result.success({"device": device, "op": op, "level": now, "muted": op == "mute"})
        new = {"set": int(level or 0), "up": now + int(level or STEP), "down": now - int(level or STEP)}[op]
        new = max(0, min(100, new))
        ep.SetMasterVolumeLevelScalar(new / 100.0, None)
        if new > 0 and ep.GetMute():
            ep.SetMute(0, None)  # turning the volume up is meant to be heard
        return Result.success({"device": device, "op": op, "level": new, "previous": now, "muted": bool(ep.GetMute())})

    return policy.run_guarded("volume_control", target, go, **_ctx(ctx))

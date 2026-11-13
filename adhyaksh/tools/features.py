"""Local tools behind the vision, performance and voice chat intents.

Every action goes through policy.run_guarded, so it is authorised by level and audited like the other tools:
  perf_stats    L0  read CPU, RAM, disk, the top memory users and the size of old temp files
  vision_detect L0  run object detection on an image the user attached
  page_open     L0  ask the UI to show one of its own pages
  temp_clean    L2  delete old temp files (needs confirmation)
  voice_control L1  change listening and speech settings (the browser still asks for microphone permission)
"""
from __future__ import annotations

from collections import defaultdict

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED, Result
from adhyaksh.safety import policy

PAGES = {"vision": "Object Detection", "performance": "PC Performance"}
VOICE_ACTIONS = {"start", "stop", "quiet", "speak_on", "speak_off", "wake_on", "wake_off", "lang"}
VOICE_LANGS = {"en-IN": "English", "hi-IN": "Hindi", "gu-IN": "Gujarati"}


def _ctx(ctx: dict | None) -> dict:
    return {"user_text": (ctx or {}).get("user_text", ""), "intent": (ctx or {}).get("intent", "")}


def perf_report(top_n: int = 3, *, ctx: dict | None = None) -> Result:
    """CPU, RAM and disk now, plus the applications using the most memory."""
    def go() -> Result:
        from adhyaksh.tools import boost
        import psutil
        s = boost.stats()
        by_name: dict[str, float] = defaultdict(float)
        for p in psutil.process_iter(["name", "memory_percent"]):
            try:
                by_name[(p.info["name"] or "?")] += float(p.info["memory_percent"] or 0.0)
            except (psutil.Error, TypeError, ValueError):
                continue
        top = sorted(by_name.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
        return Result.success({**s, "top": [{"name": n, "ram_percent": round(v, 1)} for n, v in top]})
    return policy.run_guarded("perf_stats", "system", go, **_ctx(ctx))


def temp_scan(*, ctx: dict | None = None) -> Result:
    def go() -> Result:
        from adhyaksh.tools import boost
        t = boost.scan_temp()
        return Result.success({"files": t["files"], "mb": round(t["bytes"] / (1024 * 1024), 1)})
    return policy.run_guarded("perf_stats", "temp files", go, **_ctx(ctx))


def temp_clean(*, ctx: dict | None = None, token: str | None = None) -> Result:
    """Delete temp files older than a day. L2: the first call returns a confirmation token."""
    def go() -> Result:
        from adhyaksh.tools import boost
        r = boost.clean_temp()
        return Result.success({"mb": round(r["freed_bytes"] / (1024 * 1024), 1), "skipped": r["skipped"]})
    return policy.run_guarded("temp_clean", "temp files", go, token=token, **_ctx(ctx))


def detect_objects(image_bytes: bytes, *, ctx: dict | None = None) -> Result:
    """Detect objects in an attached image. Returns counts per label, best confidence first."""
    def go() -> Result:
        from adhyaksh.vision import detector
        dets = detector.detect(image_bytes, conf=0.25, model_choice=config.get("vision_model") or "balanced")
        err = [d for d in dets if "error" in d]
        if err:
            return Result.failure(E_ACTION_FAILED, err[0]["error"])
        groups: dict[str, list[float]] = defaultdict(list)
        for d in dets:
            groups[d["label"]].append(d["confidence"])
        items = sorted(({"label": k, "count": len(v), "best": round(max(v), 2)} for k, v in groups.items()),
                       key=lambda x: (-x["count"], -x["best"]))
        return Result.success({"objects": items, "total": len(dets)})
    return policy.run_guarded("vision_detect", "image", go, **_ctx(ctx))


def open_page(slug: str, *, ctx: dict | None = None) -> Result:
    """Ask the UI to switch to one of its pages (the chat page performs the switch)."""
    def go() -> Result:
        if slug not in PAGES:
            return Result.failure(E_ACTION_FAILED, "Unknown page.")
        return Result.success({"page": slug, "title": PAGES[slug]})
    return policy.run_guarded("page_open", slug, go, **_ctx(ctx))


def voice_command(action: str, value: str = "", *, ctx: dict | None = None) -> Result:
    """Change voice settings. The chat page forwards the command to the browser control."""
    def go() -> Result:
        if action not in VOICE_ACTIONS:
            return Result.failure(E_ACTION_FAILED, "Unknown voice command.")
        if action == "start":
            config.set_value("voice_handsfree", "true")
        elif action == "stop":
            config.set_value("voice_handsfree", "false")
        elif action == "speak_on":
            config.set_value("voice_reply", "true")
        elif action == "speak_off":
            config.set_value("voice_reply", "false")
        elif action == "wake_on":
            config.set_value("voice_wake_word", "true")
        elif action == "wake_off":
            config.set_value("voice_wake_word", "false")
        elif action == "lang":
            if value not in VOICE_LANGS:
                return Result.failure(E_ACTION_FAILED, "That voice language is not supported.")
            config.set_value("voice_lang", value)
        return Result.success({"action": action, "value": value})
    return policy.run_guarded("voice_control", action, go, **_ctx(ctx))

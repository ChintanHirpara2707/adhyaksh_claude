"""Local tools behind the vision, performance and voice chat intents.

Every action goes through policy.run_guarded, so it is authorised by level and audited like the other tools:
  perf_stats    L0  read CPU, RAM, disk, the top memory users and the size of old temp files
  vision_detect L0  run object detection on an image the user attached
  page_open     L0  ask the UI to show one of its own pages
  temp_clean    L2  delete old temp files (needs confirmation)
  voice_control L1  change listening and speech settings (the browser still asks for microphone permission)
"""
from __future__ import annotations

import re
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
    token = token or (ctx or {}).get("token")
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


# ---------------------------------------------------------------------------
# Vision in chat (P5): richer scene description, named objects, small objects, OCR
# ---------------------------------------------------------------------------
_NAMED = re.compile(r"\b(?:find|look\s+for|spot|search\s+for|locate|is\s+there\s+(?:a|an|any)|are\s+there\s+(?:any)?|do\s+you\s+see\s+(?:a|an|any)?)\s+"
                    r"(?P<names>[a-z ,]+?)(?:\s+(?:in|on)\s+(?:this|the|my)\s+(?:photo|picture|image|pic))?[\s?.!]*$", re.IGNORECASE)
_SMALL = re.compile(r"\bsmall\b|\btiny\b|\bfar\b|\bdistant\b|\bchhot\w*|\bnan\w*|छोट|નાન", re.IGNORECASE)


def requested_names(text: str) -> list[str]:
    """Object names the user asked to look for ('find a mug and a stapler'), else []."""
    m = _NAMED.search(text or "")
    if not m:
        return []
    raw = re.split(r",|\band\b|\bor\b", m.group("names"))
    skip = {"a", "an", "the", "any", "some", "small", "tiny", "little", "big", "far", "distant", "all"}
    names = [" ".join(w for w in n.split() if w not in skip) for n in raw]
    generic = ("object", "objects", "thing", "things", "item", "items", "stuff", "something", "anything")
    return [n for n in names if n and not any(n == g or n.endswith(" " + g) for g in generic)][:10]


def analyze_image(image_bytes: bytes, request: str = "", *, ctx: dict | None = None) -> Result:
    """Detect objects and describe the scene (counts, positions, sizes, colours). Looks for objects the user names
    (open-vocabulary model when installed, else among the 80 known types), scans in tiles for 'small objects', and
    falls back to the 1,000-category classifier when nothing is found. L0, audited as vision_detect."""
    def go() -> Result:
        from adhyaksh.vision import descriptions, detector, scene
        names = requested_names(request)
        model = config.get("vision_model") or "balanced"
        unknown = [n for n in names if n not in descriptions.COCO_NAMES and n.rstrip("s") not in descriptions.COCO_NAMES]
        mode = "standard"
        dets = None
        if names and unknown and detector.world_available():  # never downloads: only when already installed
            dets = detector.detect_open_vocab(image_bytes, names)
            mode = "named"
            if dets and "error" in dets[0]:
                dets, mode = None, "standard"
        if dets is None and _SMALL.search(request or ""):
            dets, mode = detector.detect_tiled(image_bytes, conf=0.25, model_choice=model), "tiled"
        elif dets is None:
            dets = detector.detect(image_bytes, conf=0.25, model_choice=model)
        err = [d for d in dets if "error" in d]
        if err:
            return Result.failure(E_ACTION_FAILED, err[0]["error"])
        desc = scene.describe(image_bytes, dets)
        guesses = []
        if not dets:
            g = detector.classify(image_bytes)
            guesses = g[:3] if isinstance(g, list) else []
        found = {d["label"] for d in dets}
        asked = [{"name": n, "found": n in found or n.rstrip("s") in found,
                  "known": n not in unknown or mode == "named"} for n in names]
        return Result.success({**desc, "mode": mode, "requested": asked, "guesses": guesses,
                               "objects": [{"label": i["label"], "count": i["count"], "best": i["confidence"]} for i in desc["items"]]})
    return policy.run_guarded("vision_detect", "image", go, **_ctx(ctx))


def read_text(image_bytes: bytes, *, ctx: dict | None = None) -> Result:
    """Text printed in an image (OCR, offline). L0, audited as ocr_read."""
    def go() -> Result:
        from adhyaksh.vision import ocr
        return ocr.read(image_bytes)
    return policy.run_guarded("ocr_read", "image", go, **_ctx(ctx))

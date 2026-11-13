"""Object detection with Ultralytics YOLOv8 (lazy import, cached models)."""
from __future__ import annotations

import hashlib
import io
import re
from pathlib import Path

from PIL import Image, ImageStat

from adhyaksh import config

_MAX_BYTES = 10 * 1024 * 1024
_MODELS: dict[str, object] = {}
_CLASSIFIER: object | None = None
_DETECT_CACHE: dict[str, list[dict]] = {}
_CLASSIFY_CACHE: dict[str, list[dict] | str] = {}
_RAW_CACHE: dict[str, list[dict]] = {}

DETECTION_MODELS = {
    "fast": "yolov8n.pt",
    "balanced": "yolov8s.pt",
    "accurate": "yolov8m.pt",
}
CLASSIFIER_MODEL = "yolov8n-cls.pt"


def _model_dir() -> Path:
    return config.models_dir()


def _model_path(name: str) -> Path:
    d = _model_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d / name


def _load_detection(choice: str):
    """Load (and cache) the detection model for the given choice."""
    if choice not in _MODELS:
        from ultralytics import YOLO

        name = DETECTION_MODELS.get(choice, DETECTION_MODELS["balanced"])
        path = str(_model_path(name))
        last_exc: Exception | None = None
        try:
            _MODELS[choice] = YOLO(path)
        except Exception as exc:  # download may fail
            last_exc = exc
            p = _model_path(name)
            if p.exists():  # fall back to weights already on disk
                try:
                    _MODELS[choice] = YOLO(str(p))
                except Exception as exc2:
                    last_exc = exc2
        if last_exc is not None and choice not in _MODELS:
            raise last_exc
    return _MODELS[choice]


def _load_classifier():
    """Load (and cache) the YOLOv8 classification fallback model."""
    global _CLASSIFIER
    if _CLASSIFIER is None:
        from ultralytics import YOLO

        path = str(_model_path(CLASSIFIER_MODEL))
        last_exc: Exception | None = None
        try:
            _CLASSIFIER = YOLO(path)
        except Exception as exc:
            last_exc = exc
            p = _model_path(CLASSIFIER_MODEL)
            if p.exists():
                try:
                    _CLASSIFIER = YOLO(str(p))
                except Exception as exc2:
                    last_exc = exc2
        if last_exc is not None and _CLASSIFIER is None:
            raise last_exc
    return _CLASSIFIER


def _image_kind(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def detect(image_bytes: bytes, conf: float = 0.4, imgsz: int = 640,
           model_choice: str = "balanced") -> list[dict]:
    """Run YOLOv8 detection on image bytes.

    Returns a list of {"label", "confidence", "box"}.
    On error returns a list with a single {"error": <message>} dict.
    """
    if len(image_bytes) > _MAX_BYTES:
        return [{"error": "File too large. Maximum 10 MB."}]
    kind = _image_kind(image_bytes)
    if kind not in ("jpeg", "png", "webp"):
        return [{"error": "Unsupported file type. Use JPG, PNG or WEBP."}]
    cache_key = f"{hashlib.sha1(image_bytes).hexdigest()}:{conf}:{imgsz}:{model_choice}"
    if cache_key in _DETECT_CACHE:
        return _DETECT_CACHE[cache_key]
    try:
        model = _load_detection(model_choice)
    except ImportError:
        return [{"error": "Object detection needs the ultralytics package. Install it with: pip install ultralytics"}]
    except Exception as exc:  # download or load failure
        return [{"error": f"Model load failed: {exc}. Check your internet connection or place the weights file in models/."}]
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return [{"error": "The image could not be read."}]
    try:
        results = model.predict(img, conf=conf, imgsz=imgsz, verbose=False)
    except Exception as exc:
        return [{"error": f"Detection failed: {exc}"}]
    detections: list[dict] = []
    for r in results:
        names = r.names
        for box in r.boxes or []:
            cls = int(box.cls[0])
            detections.append({
                "label": names.get(cls, str(cls)),
                "confidence": float(box.conf[0]),
                "box": [float(v) for v in box.xyxy[0]],
            })
    _DETECT_CACHE[cache_key] = detections
    return detections


def detect_raw(image_bytes: bytes, model_choice: str = "balanced", imgsz: int = 640) -> list[dict]:
    """Return raw detections at confidence 0.05 (top 5 by confidence)."""
    dets = detect(image_bytes, conf=0.05, imgsz=imgsz, model_choice=model_choice)
    error = [d for d in dets if "error" in d]
    if error:
        return []
    dets_sorted = sorted(dets, key=lambda d: d["confidence"], reverse=True)
    return dets_sorted[:5]


def average_brightness(image_bytes: bytes) -> float | None:
    """Return average brightness 0-255, or None if unreadable."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        stat = ImageStat.Stat(img)
        return float(stat.mean[0])
    except Exception:
        return None


def classify(image_bytes: bytes, imgsz: int = 640) -> list[dict] | str:
    """Run YOLOv8 classification fallback. Returns top guesses or an error string."""
    cache_key = f"{hashlib.sha1(image_bytes).hexdigest()}:{imgsz}:classify"
    if cache_key in _CLASSIFY_CACHE:
        return _CLASSIFY_CACHE[cache_key]
    try:
        model = _load_classifier()
    except ImportError:
        return "Object detection needs the ultralytics package. Install it with: pip install ultralytics"
    except Exception as exc:
        return f"Classifier load failed: {exc}. Check your internet connection or place the weights file in models/."
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return "The image could not be read."
    try:
        results = model(img, imgsz=imgsz, verbose=False)
    except Exception as exc:
        return f"Classification failed: {exc}"
    guesses: list[dict] = []
    for r in results:
        probs = r.probs
        if probs is None:
            continue
        names = r.names
        top5 = probs.top5 or []
        top5conf = probs.top5conf or []
        for cls, conf in zip(top5, top5conf):
            guesses.append({
                "label": names.get(int(cls), str(cls)),
                "confidence": float(conf),
            })
    _CLASSIFY_CACHE[cache_key] = guesses
    return guesses


# ---------------------------------------------------------------------------
# Wider coverage. The standard detector only knows the 80 COCO classes. These helpers add
# (1) tiled detection for small objects, (2) optional open-vocabulary detection with YOLO-World
# for any words you type, and (3) the 1000 ImageNet classes through classify().
# ---------------------------------------------------------------------------

WORLD_MODEL = "yolov8s-worldv2.pt"
_WORLD: dict[str, object] = {}
_TILE_CACHE: dict[str, list[dict]] = {}
_WORLD_CACHE: dict[str, list[dict]] = {}
MAX_OPEN_CLASSES = 30


def _read_image(image_bytes: bytes):
    """Validate and open image bytes. Returns (image, None) or (None, error dict list)."""
    if len(image_bytes) > _MAX_BYTES:
        return None, [{"error": "File too large. Maximum 10 MB."}]
    if _image_kind(image_bytes) not in ("jpeg", "png", "webp"):
        return None, [{"error": "Unsupported file type. Use JPG, PNG or WEBP."}]
    try:
        return Image.open(io.BytesIO(image_bytes)).convert("RGB"), None
    except Exception:
        return None, [{"error": "The image could not be read."}]


def _to_dets(results, dx: float = 0.0, dy: float = 0.0) -> list[dict]:
    out: list[dict] = []
    for r in results:
        names = r.names
        for box in r.boxes or []:
            cls = int(box.cls[0])
            x1, y1, x2, y2 = (float(v) for v in box.xyxy[0])
            out.append({"label": names.get(cls, str(cls)), "confidence": float(box.conf[0]),
                        "box": [x1 + dx, y1 + dy, x2 + dx, y2 + dy]})
    return out


def iou(a: list[float], b: list[float]) -> float:
    ix1, iy1, ix2, iy2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, ix2 - ix1) * max(0.0, iy2 - iy1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def nms(dets: list[dict], iou_threshold: float = 0.5) -> list[dict]:
    """Per-label non-maximum suppression; keeps the most confident box of each overlapping group."""
    kept: list[dict] = []
    for d in sorted(dets, key=lambda x: x["confidence"], reverse=True):
        if all(k["label"] != d["label"] or iou(k["box"], d["box"]) < iou_threshold for k in kept):
            kept.append(d)
    return kept


def _tiles(w: int, h: int, grid: int, overlap: float = 0.2) -> list[tuple[int, int, int, int]]:
    tw, th = w / grid, h / grid
    ox, oy = tw * overlap, th * overlap
    out = []
    for gy in range(grid):
        for gx in range(grid):
            out.append((int(max(0, gx * tw - ox)), int(max(0, gy * th - oy)),
                        int(min(w, (gx + 1) * tw + ox)), int(min(h, (gy + 1) * th + oy))))
    return out


def detect_tiled(image_bytes: bytes, conf: float = 0.25, imgsz: int = 640, model_choice: str = "balanced",
                 grid: int = 2) -> list[dict]:
    """Detect on the whole image plus a grid of overlapping tiles, then merge with NMS.

    Small or distant objects that vanish at 640 px become large enough to find in a tile."""
    img, err = _read_image(image_bytes)
    if err:
        return err
    key = f"{hashlib.sha1(image_bytes).hexdigest()}:{conf}:{imgsz}:{model_choice}:{grid}"
    if key in _TILE_CACHE:
        return _TILE_CACHE[key]
    try:
        model = _load_detection(model_choice)
    except ImportError:
        return [{"error": "Object detection needs the ultralytics package. Install it with: pip install ultralytics"}]
    except Exception as exc:
        return [{"error": f"Model load failed: {exc}. Check your internet connection or place the weights file in models/."}]
    dets: list[dict] = []
    try:
        dets += _to_dets(model.predict(img, conf=conf, imgsz=imgsz, verbose=False))
        for (x1, y1, x2, y2) in _tiles(img.width, img.height, max(2, min(grid, 4))):
            tile = img.crop((x1, y1, x2, y2))
            dets += _to_dets(model.predict(tile, conf=conf, imgsz=imgsz, verbose=False), x1, y1)
    except Exception as exc:
        return [{"error": f"Detection failed: {exc}"}]
    merged = nms(dets)
    _TILE_CACHE[key] = merged
    return merged


def parse_classes(text: str) -> list[str]:
    """Split user text like 'mug, stapler; red pen' into clean unique class names."""
    seen: dict[str, None] = {}
    for part in re.split(r"[,;\n]+", text or ""):
        name = " ".join(part.split()).lower()[:40]
        if name:
            seen[name] = None
    return list(seen)[:MAX_OPEN_CLASSES]


def _load_world():
    if "m" not in _WORLD:
        from ultralytics import YOLOWorld

        path = _model_path(WORLD_MODEL)
        _WORLD["m"] = YOLOWorld(str(path) if path.exists() else WORLD_MODEL)
        _WORLD["classes"] = None
    return _WORLD["m"]


def detect_open_vocab(image_bytes: bytes, classes: list[str], conf: float = 0.2, imgsz: int = 640) -> list[dict]:
    """Detect any objects you name, using YOLO-World (open vocabulary). Needs extra downloads:
    the YOLO-World weights and the CLIP text encoder (ultralytics fetches both on first use)."""
    classes = [c for c in classes if c][:MAX_OPEN_CLASSES]
    if not classes:
        return [{"error": "Type at least one object name to look for."}]
    img, err = _read_image(image_bytes)
    if err:
        return err
    key = f"{hashlib.sha1(image_bytes).hexdigest()}:{conf}:{imgsz}:{'|'.join(classes)}"
    if key in _WORLD_CACHE:
        return _WORLD_CACHE[key]
    try:
        model = _load_world()
    except ImportError:
        return [{"error": "Open-vocabulary detection needs a recent ultralytics package (pip install -U ultralytics)."}]
    except Exception as exc:
        return [{"error": f"YOLO-World could not be loaded: {exc}. It needs an internet connection the first time "
                          f"to download {WORLD_MODEL} and the CLIP text encoder."}]
    try:
        if _WORLD.get("classes") != classes:
            model.set_classes(classes)
            _WORLD["classes"] = list(classes)
        dets = nms(_to_dets(model.predict(img, conf=conf, imgsz=imgsz, verbose=False)))
    except Exception as exc:
        return [{"error": f"Open-vocabulary detection failed: {exc}"}]
    _WORLD_CACHE[key] = dets
    return dets

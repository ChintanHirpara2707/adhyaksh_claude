"""Object detection with Ultralytics YOLOv8 (lazy import, cached models)."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image

from adhyaksh import config

_MAX_BYTES = 10 * 1024 * 1024
_MODELS: dict[str, object] = {}
_CLASSIFIER: object | None = None

DETECTION_MODELS = {
    "fast": "yolov8n.pt",
    "balanced": "yolov8s.pt",
    "accurate": "yolov8m.pt",
}
CLASSIFIER_MODEL = "yolov8n-cls.pt"
_MODEL_DIR = Path("models")


def _model_path(name: str) -> Path:
    _MODEL_DIR.mkdir(parents=True, exist_ok=True)
    return _MODEL_DIR / name


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
    return detections


def detect_raw(image_bytes: bytes, model_choice: str = "balanced") -> list[dict]:
    """Return raw detections at confidence 0.05 (top 5 by confidence)."""
    dets = detect(image_bytes, conf=0.05, model_choice=model_choice)
    error = [d for d in dets if "error" in d]
    if error:
        return []
    dets_sorted = sorted(dets, key=lambda d: d["confidence"], reverse=True)
    return dets_sorted[:5]


def average_brightness(image_bytes: bytes) -> float | None:
    """Return average brightness 0-255, or None if unreadable."""
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("L")
        try:
            pixels = list(img.get_flattened_data())  # Pillow >= 14
        except AttributeError:
            pixels = list(img.getdata())  # older Pillow
        if not pixels:
            return None
        return sum(pixels) / len(pixels)
    except Exception:
        return None


def classify(image_bytes: bytes, imgsz: int = 640) -> list[dict] | str:
    """Run YOLOv8 classification fallback. Returns top guesses or an error string."""
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
    return guesses

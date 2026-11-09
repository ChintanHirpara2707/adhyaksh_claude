"""Object detection with Ultralytics YOLOv8n (lazy import, cached model)."""
from __future__ import annotations

from pathlib import Path

_MAX_BYTES = 10 * 1024 * 1024
_MODEL = None
_MODEL_PATH = Path("models") / "yolov8n.pt"


def _load_model():
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO
        _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        _MODEL = YOLO(str(_MODEL_PATH))
    return _MODEL


def _image_kind(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def detect(image_bytes: bytes, conf: float = 0.4) -> list[dict]:
    """Run YOLOv8n detection on image bytes.

    Returns a list of {"label": str, "confidence": float, "box": [x1, y1, x2, y2]}.
    On error returns a list with a single {"error": <message>} dict.
    """
    if len(image_bytes) > _MAX_BYTES:
        return [{"error": "File too large. Maximum 10 MB."}]
    kind = _image_kind(image_bytes)
    if kind not in ("jpeg", "png", "webp"):
        return [{"error": "Unsupported file type. Use JPG, PNG or WEBP."}]
    try:
        model = _load_model()
    except ImportError:
        return [{"error": "Object detection needs the ultralytics package. Install it with: pip install ultralytics"}]
    except Exception as exc:  # download or load failure
        return [{"error": f"Model load failed: {exc}"}]
    try:
        results = model(image_bytes, conf=conf, verbose=False)
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

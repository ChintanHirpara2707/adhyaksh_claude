"""Read printed text in images (OCR), offline.

Uses RapidOCR (ONNX models bundled with the package, about 24 MB installed; no download at run time). It reads
Latin script (English, numbers, romanised Hindi and Gujarati) and Chinese. Devanagari and Gujarati script are
not supported by its models; for those, Tesseract with the hin and guj language data is used when it is
installed (optional, separate program).
"""
from __future__ import annotations

import io
import shutil
import threading
import time

from adhyaksh.result import E_ACTION_FAILED, Result

_ENGINE = {"obj": None}
_LOCK = threading.Lock()
MAX_BYTES = 10 * 1024 * 1024


def installed() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        return True
    except Exception:
        return False


def tesseract_available() -> bool:
    try:
        import pytesseract  # noqa: F401
    except Exception:
        return False
    return shutil.which("tesseract") is not None


def _engine():
    with _LOCK:
        if _ENGINE["obj"] is None:
            from rapidocr_onnxruntime import RapidOCR
            _ENGINE["obj"] = RapidOCR()
        return _ENGINE["obj"]


def order_lines(items: list[dict]) -> list[dict]:
    """Reading order: top to bottom; boxes whose vertical centres are close count as one row, read left to right."""
    rows: list[list[dict]] = []
    for it in sorted(items, key=lambda r: r["box"][1]):
        cy = (it["box"][1] + it["box"][3]) / 2
        h = max(1.0, it["box"][3] - it["box"][1])
        for row in rows:
            rcy = sum((r["box"][1] + r["box"][3]) / 2 for r in row) / len(row)
            if abs(rcy - cy) < 0.5 * h:
                row.append(it)
                break
        else:
            rows.append([it])
    out = []
    for row in rows:
        out.extend(sorted(row, key=lambda r: r["box"][0]))
    return out


def read(image_bytes: bytes, min_conf: float = 0.5) -> Result:
    """Text found in an image. Returns {text, lines: [{text, conf, box}], engine, ms}."""
    if not image_bytes or len(image_bytes) > MAX_BYTES:
        return Result.failure(E_ACTION_FAILED, "The image is empty or larger than 10 MB.")
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return Result.failure(E_ACTION_FAILED, "The image could not be read.")
    t0 = time.perf_counter()
    lines: list[dict] = []
    engine = ""
    if installed():
        import numpy as np
        try:
            result, _ = _engine()(np.asarray(img))
        except Exception as exc:  # broken model files
            return Result.failure(E_ACTION_FAILED, f"Text recognition failed ({type(exc).__name__}).")
        for box, text, conf in result or []:
            xs, ys = [p[0] for p in box], [p[1] for p in box]
            if float(conf) >= min_conf and str(text).strip():
                lines.append({"text": str(text).strip(), "conf": round(float(conf), 2),
                              "box": [float(min(xs)), float(min(ys)), float(max(xs)), float(max(ys))]})
        engine = "rapidocr"
    if not lines and tesseract_available():
        import pytesseract
        try:
            text = pytesseract.image_to_string(img, lang="eng+hin+guj")
        except Exception:
            text = pytesseract.image_to_string(img)
        lines = [{"text": t.strip(), "conf": 1.0, "box": [0, i, 1, i + 1]} for i, t in enumerate(text.splitlines()) if t.strip()]
        engine = "tesseract"
    if not engine:
        return Result.failure(E_ACTION_FAILED, "Text recognition needs the rapidocr_onnxruntime package (pip install rapidocr_onnxruntime).")
    lines = order_lines(lines)
    return Result.success({"text": "\n".join(x["text"] for x in lines), "lines": lines, "engine": engine,
                           "ms": round((time.perf_counter() - t0) * 1000)})

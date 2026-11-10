"""Tests for object detection with a fake model (no ultralytics, no network, no camera)."""
from __future__ import annotations

import hashlib
import io
import json
from PIL import Image

from adhyaksh.vision import detector, descriptions


class _FakeResult:
    def __init__(self, names, boxes):
        self.names = names
        self.boxes = boxes


class _FakeBox:
    def __init__(self, cls, conf, xyxy):
        self.cls = [cls]
        self.conf = [conf]
        self.xyxy = [xyxy]


class _FakeModel:
    def __init__(self, path):
        self.path = path
        self.received = None
        self.predict_kwargs = None
        self.call_count = 0

    def predict(self, img, conf=0.4, imgsz=640, verbose=False):
        self.call_count += 1
        self.received = img
        self.predict_kwargs = {"conf": conf, "imgsz": imgsz, "verbose": verbose}
        return [_FakeResult({0: "person", 1: "bicycle", 41: "cup"},
                            [_FakeBox(0, 0.9, [10, 20, 100, 120]),
                             _FakeBox(0, 0.7, [110, 30, 200, 130]),
                             _FakeBox(41, 0.85, [50, 60, 90, 110])])]


class _EmptyResult:
    names = {}
    boxes = []


class _EmptyModel:
    def predict(self, img, conf=0.4, imgsz=640, verbose=False):
        return [_EmptyResult()]


class _FakeClassifierResult:
    def __init__(self, names, confs):
        class _Probs:
            def __init__(self, n, c):
                self.top5 = list(n.keys())
                self.top5conf = c
        self.probs = _Probs(names, confs)
        self.names = names


class _FakeClassifier:
    def __init__(self, path):
        self.path = path
        self.received = None
        self.predict_kwargs = None
        self.call_count = 0

    def __call__(self, img, imgsz=640, verbose=False):
        self.call_count += 1
        self.received = img
        self.predict_kwargs = {"imgsz": imgsz, "verbose": verbose}
        return [_FakeClassifierResult({0: "person", 1: "bicycle", 2: "cup"},
                                      [0.9, 0.7, 0.6])]


def _make_load(fake_model):
    def load(choice):
        return fake_model
    return load


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------

def test_detect_respects_model_choice(monkeypatch):
    fake = _FakeModel("models/yolov8n.pt")
    monkeypatch.setattr(detector, "_MODELS", {})
    monkeypatch.setattr(detector, "_DETECT_CACHE", {})
    monkeypatch.setattr(detector, "_load_detection", _make_load(fake))
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    img = buf.getvalue()
    dets = detector.detect(img, conf=0.25, imgsz=640, model_choice="fast")
    assert len(dets) == 3
    assert fake.path.endswith("yolov8n.pt")
    assert fake.predict_kwargs["conf"] == 0.25
    assert fake.predict_kwargs["imgsz"] == 640


def test_detect_uses_imgsz(monkeypatch):
    fake = _FakeModel("models/yolov8s.pt")
    monkeypatch.setattr(detector, "_MODELS", {})
    monkeypatch.setattr(detector, "_DETECT_CACHE", {})
    monkeypatch.setattr(detector, "_load_detection", _make_load(fake))
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    img = buf.getvalue()
    detector.detect(img, model_choice="balanced", imgsz=960)
    assert fake.predict_kwargs["imgsz"] == 960


def test_detect_grouping_and_counts(monkeypatch):
    fake = _FakeModel("models/yolov8s.pt")
    monkeypatch.setattr(detector, "_MODELS", {})
    monkeypatch.setattr(detector, "_DETECT_CACHE", {})
    monkeypatch.setattr(detector, "_load_detection", _make_load(fake))
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    img = buf.getvalue()
    dets = detector.detect(img, conf=0.25)
    assert len(dets) == 3
    by_label: dict[str, int] = {}
    for d in dets:
        by_label[d["label"]] = by_label.get(d["label"], 0) + 1
    assert by_label == {"person": 2, "cup": 1}
    best_person = max((d for d in dets if d["label"] == "person"), key=lambda x: x["confidence"])
    assert best_person["confidence"] == 0.9
    assert isinstance(fake.received, Image.Image)
    assert not isinstance(fake.received, bytes)


def test_detect_rejects_corrupted_image(monkeypatch):
    monkeypatch.setattr(detector, "_MODELS", {})
    fake = _FakeModel("models/yolov8s.pt")
    monkeypatch.setattr(detector, "_load_detection", _make_load(fake))
    dets = detector.detect(b"\xff\xd8\xff" + b"\x00" * 10)
    assert len(dets) == 1 and "could not be read" in dets[0]["error"].lower()


def test_detect_rejects_too_large(monkeypatch):
    monkeypatch.setattr(detector, "_MODELS", {})
    big = b"\xff\xd8\xff" + b"\x00" * (detector._MAX_BYTES + 1)
    dets = detector.detect(big)
    assert len(dets) == 1 and "too large" in dets[0]["error"].lower()


def test_detect_rejects_wrong_type(monkeypatch):
    monkeypatch.setattr(detector, "_MODELS", {})
    dets = detector.detect(b"not an image")
    assert len(dets) == 1 and "unsupported" in dets[0]["error"].lower()


def test_detect_missing_ultralytics(monkeypatch):
    monkeypatch.setattr(detector, "_MODELS", {})

    def _fail_load(choice):
        raise ImportError("No module named 'ultralytics'")

    monkeypatch.setattr(detector, "_load_detection", _fail_load)
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    dets = detector.detect(buf.getvalue())
    assert len(dets) == 1 and "ultralytics" in dets[0]["error"]


# ---------------------------------------------------------------------------
# Cache behavior tests (identical input does not re-run, slider change does)
# ---------------------------------------------------------------------------

def test_camera_processed_when_upload_empty(monkeypatch):
    """Camera bytes are processed as a separate source even when upload is None."""
    fake = _FakeModel("models/yolov8s.pt")
    monkeypatch.setattr(detector, "_MODELS", {})
    monkeypatch.setattr(detector, "_DETECT_CACHE", {})
    monkeypatch.setattr(detector, "_load_detection", _make_load(fake))

    # Simulate upload being None, camera having bytes
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    camera_bytes = buf.getvalue()

    # Camera input processes its own bytes
    dets = detector.detect(camera_bytes, conf=0.25, imgsz=640, model_choice="balanced")
    assert len(dets) == 3
    assert isinstance(fake.received, Image.Image)


def test_slider_change_reruns_detection(monkeypatch):
    """Changing conf/imgsz/model_choice produces a new cache key -> re-runs predict."""
    fake = _FakeModel("models/yolov8s.pt")
    monkeypatch.setattr(detector, "_MODELS", {})
    monkeypatch.setattr(detector, "_DETECT_CACHE", {})
    monkeypatch.setattr(detector, "_load_detection", _make_load(fake))
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    img = buf.getvalue()

    # First call
    detector.detect(img, conf=0.25, imgsz=640, model_choice="balanced")
    first_calls = fake.call_count

    # Same input -> should NOT re-run (same cache key)
    detector.detect(img, conf=0.25, imgsz=640, model_choice="balanced")
    assert fake.call_count == first_calls, "identical input should not re-run detect"

    # Slider change (conf) -> new cache key -> re-run
    detector.detect(img, conf=0.50, imgsz=640, model_choice="balanced")
    assert fake.call_count == first_calls + 1, "changed conf should re-run detect"

    # Image size change -> re-run
    detector.detect(img, conf=0.50, imgsz=960, model_choice="balanced")
    assert fake.call_count == first_calls + 2, "changed imgsz should re-run detect"


def test_identical_input_no_rerun(monkeypatch):
    """Same bytes, conf, imgsz, model_choice -> predict called only once."""
    fake = _FakeModel("models/yolov8s.pt")
    monkeypatch.setattr(detector, "_MODELS", {})
    monkeypatch.setattr(detector, "_DETECT_CACHE", {})
    monkeypatch.setattr(detector, "_load_detection", _make_load(fake))
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    img = buf.getvalue()

    detector.detect(img, conf=0.25, imgsz=640, model_choice="balanced")
    n1 = fake.call_count

    # Same input again
    detector.detect(img, conf=0.25, imgsz=640, model_choice="balanced")
    assert fake.call_count == n1, "identical input must not re-run detection"


# ---------------------------------------------------------------------------
# Classifier fallback tests
# ---------------------------------------------------------------------------

def test_detect_returns_empty_then_classify_runs(monkeypatch):
    """When detection returns nothing, classify runs as fallback."""
    monkeypatch.setattr(detector, "_MODELS", {})
    monkeypatch.setattr(detector, "_DETECT_CACHE", {})
    monkeypatch.setattr(detector, "_CLASSIFY_CACHE", {})
    monkeypatch.setattr(detector, "_load_detection", lambda c: _EmptyModel())
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    img = buf.getvalue()
    assert detector.detect(img) == []

    monkeypatch.setattr(detector, "_CLASSIFIER", None)
    monkeypatch.setattr(detector, "_load_classifier", lambda: _FakeClassifier("models/yolov8n-cls.pt"))
    result = detector.classify(img)
    assert isinstance(result, list)
    assert len(result) == 3
    assert result[0]["label"] == "person"
    assert result[0]["confidence"] == 0.9


def test_classify_top3_format(monkeypatch):
    monkeypatch.setattr(detector, "_CLASSIFIER", None)
    monkeypatch.setattr(detector, "_CLASSIFY_CACHE", {})
    monkeypatch.setattr(detector, "_load_classifier", lambda: _FakeClassifier("models/yolov8n-cls.pt"))
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    result = detector.classify(buf.getvalue())
    assert isinstance(result, list)
    assert len(result) <= 3
    for g in result:
        assert "label" in g and "confidence" in g


# ---------------------------------------------------------------------------
# Description tests
# ---------------------------------------------------------------------------

def test_describe_known_labels(monkeypatch):
    assert descriptions.describe("person") == "A person is a human being. People walk, talk, work, and carry out daily activities."
    assert descriptions.describe("cup") == "A cup is a small round container used for drinking. It holds coffee, tea, or other hot or cold drinks."
    assert descriptions.describe("bicycle") == "A bicycle is a two-wheeled vehicle you ride by pedaling. It is used for transport, exercise, and recreation."
    assert descriptions.describe("laptop") == "A laptop is a portable computer with a screen and keyboard. It is used for work, study, and entertainment anywhere."
    assert descriptions.describe("toothbrush") == "A toothbrush is a small brush used for cleaning teeth. It is used with toothpaste for oral hygiene."


def test_describe_unknown_label(monkeypatch):
    assert descriptions.describe("notacoco") == "A notacoco is an object detected in the image. It is commonly seen in everyday scenes."


# ---------------------------------------------------------------------------
# Details values tests
# ---------------------------------------------------------------------------

def test_detect_raw_top5(monkeypatch):
    fake = _FakeModel("models/yolov8s.pt")
    monkeypatch.setattr(detector, "_MODELS", {})
    monkeypatch.setattr(detector, "_load_detection", _make_load(fake))
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "red").save(buf, format="PNG")
    img = buf.getvalue()
    raw = detector.detect_raw(img, model_choice="fast", imgsz=640)
    assert len(raw) == 3
    assert raw[0]["label"] == "person"
    assert raw[0]["confidence"] == 0.9
    assert fake.predict_kwargs["conf"] == 0.05
    assert fake.predict_kwargs["imgsz"] == 640


def test_average_brightness(monkeypatch):
    monkeypatch.setattr(detector, "_MODELS", {})
    buf = io.BytesIO()
    Image.new("RGB", (10, 10), "white").save(buf, format="PNG")
    img = buf.getvalue()
    bright = detector.average_brightness(img)
    assert bright is not None
    assert 0 <= bright <= 255
    assert bright == 255.0


# ---------------------------------------------------------------------------
# Wikipedia lookup tests (fake response, no network)
# ---------------------------------------------------------------------------

class _FakeResponse:
    def __init__(self, data: dict):
        self._data = data

    def read(self):
        return json.dumps(self._data).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeUrlopen:
    def __init__(self, data: dict | None = None, fail: bool = False):
        self._data = data
        self._fail = fail
        self.called_url = None

    def __call__(self, req, timeout=None):
        self.called_url = req.full_url if hasattr(req, "full_url") else str(req)
        if self._fail:
            raise OSError("network down")
        return _FakeResponse(self._data or {})

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_wikipedia_summary(monkeypatch):
    data = {
        "extract": "A mouse is a handheld device used to control a computer cursor. It is moved on a desk to point and click.",
        "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Computer_mouse"}},
    }
    fake = _FakeUrlopen(data)
    monkeypatch.setattr(descriptions.urllib.request, "urlopen", fake)
    result = descriptions.wikipedia("mouse")
    assert "Computer mouse" in result or "A mouse is a handheld" in result
    assert "More from Wikipedia" in result
    assert fake.called_url.startswith("https://en.wikipedia.org/api/rest_v1/page/summary/")


def test_wikipedia_failure_returns_empty(monkeypatch):
    fake = _FakeUrlopen(fail=True)
    monkeypatch.setattr(descriptions.urllib.request, "urlopen", fake)
    result = descriptions.wikipedia("person")
    assert result == ""

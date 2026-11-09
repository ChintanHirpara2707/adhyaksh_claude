"""Tests for object detection with a fake model (no ultralytics, no network, no camera)."""
from __future__ import annotations

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

    def __call__(self, image_bytes, conf=0.4, verbose=False):
        return [_FakeResult({0: "person", 1: "bicycle", 41: "cup"},
                            [_FakeBox(0, 0.9, [10, 20, 100, 120]),
                             _FakeBox(0, 0.7, [110, 30, 200, 130]),
                             _FakeBox(41, 0.85, [50, 60, 90, 110])])]


def test_describe_known_labels(monkeypatch):
    assert descriptions.describe("person") == "A person is a human being."
    assert descriptions.describe("cup") == "A cup is a small round container used for drinking."
    assert descriptions.describe("bicycle") == "A bicycle is a two-wheeled vehicle you ride by pedaling."
    assert descriptions.describe("laptop") == "A laptop is a portable computer with a screen and keyboard."
    assert descriptions.describe("toothbrush") == "A toothbrush is a small brush used for cleaning teeth."


def test_describe_unknown_label(monkeypatch):
    assert descriptions.describe("notacoco") == "A notacoco is an object detected in the image."


def test_detect_grouping_and_counts(monkeypatch):
    monkeypatch.setattr(detector, "_MODEL", None)
    monkeypatch.setattr(detector, "_load_model", lambda: _FakeModel("models/yolov8n.pt"))
    img = b"\xff\xd8\xff" + b"\x00" * 100
    dets = detector.detect(img)
    assert len(dets) == 3
    by_label: dict[str, int] = {}
    for d in dets:
        by_label[d["label"]] = by_label.get(d["label"], 0) + 1
    assert by_label == {"person": 2, "cup": 1}
    best_person = max((d for d in dets if d["label"] == "person"), key=lambda x: x["confidence"])
    assert best_person["confidence"] == 0.9


def test_detect_rejects_too_large(monkeypatch):
    monkeypatch.setattr(detector, "_MODEL", None)
    big = b"\xff\xd8\xff" + b"\x00" * (detector._MAX_BYTES + 1)
    dets = detector.detect(big)
    assert len(dets) == 1 and "too large" in dets[0]["error"].lower()


def test_detect_rejects_wrong_type(monkeypatch):
    monkeypatch.setattr(detector, "_MODEL", None)
    dets = detector.detect(b"not an image")
    assert len(dets) == 1 and "unsupported" in dets[0]["error"].lower()


def test_detect_missing_ultralytics(monkeypatch):
    monkeypatch.setattr(detector, "_MODEL", None)

    def _fail_load():
        raise ImportError("No module named 'ultralytics'")

    monkeypatch.setattr(detector, "_load_model", _fail_load)
    dets = detector.detect(b"\xff\xd8\xff" + b"\x00" * 10)
    assert len(dets) == 1 and "ultralytics" in dets[0]["error"]

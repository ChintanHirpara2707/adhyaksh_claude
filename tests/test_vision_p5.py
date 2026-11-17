"""P5 vision: OCR, richer scene descriptions, named and small objects in chat."""
import io
import os
from pathlib import Path

import pytest
from PIL import Image

from adhyaksh import db
from adhyaksh.chat import context, engine
from adhyaksh.result import Result
from adhyaksh.tools import features, system
from adhyaksh.vision import detector, ocr, scene
from tests.helpers import fresh_env

os.environ["ADHYAKSH_NO_OPEN"] = "1"
SIGN = Path(__file__).resolve().parent / "data" / "sign.png"


def _png(w=600, h=400, left=(200, 30, 40), right=(40, 90, 200)):
    img = Image.new("RGB", (w, h), (240, 240, 240))
    img.paste(Image.new("RGB", (150, 300), left), (20, 50))
    img.paste(Image.new("RGB", (100, 100), right), (470, 20))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


DETS = [{"label": "person", "confidence": 0.9, "box": [20, 50, 170, 350]},
        {"label": "person", "confidence": 0.7, "box": [200, 300, 230, 330]},
        {"label": "cup", "confidence": 0.8, "box": [470, 20, 570, 120]}]


def test_scene_description_counts_positions_sizes_colours():
    d = scene.describe(_png(), DETS)
    assert d["summary"].startswith("I can see 2 people and 1 cup.")
    person = next(i for i in d["items"] if i["label"] == "person")
    cup = next(i for i in d["items"] if i["label"] == "cup")
    assert person["position"] == "on the left" and person["size"] == "medium-sized" and person["color"] == "red"
    assert cup["position"] == "at the top right" and cup["size"] == "small" and cup["color"] == "blue"
    assert "The largest person is on the left" in d["summary"]
    assert scene.describe(_png(), [])["summary"].startswith("I could not recognise")


def test_colour_names_and_plurals():
    assert scene.color_name((250, 250, 250)) == "white" and scene.color_name((10, 10, 10)) == "black"
    assert scene.color_name((50, 160, 60)) == "green" and scene.plural("knife", 2) == "knives" and scene.plural("cup", 3) == "cups"


def test_reading_order():
    items = [{"text": "B", "box": [300, 10, 350, 30]}, {"text": "A", "box": [10, 12, 60, 32]}, {"text": "C", "box": [10, 60, 60, 80]}]
    assert [x["text"] for x in ocr.order_lines(items)] == ["A", "B", "C"]


@pytest.mark.skipif(not ocr.installed(), reason="rapidocr_onnxruntime not installed")
def test_real_ocr_reads_a_sign():
    res = ocr.read(SIGN.read_bytes())
    assert res.ok and res.data["engine"] == "rapidocr"
    assert res.data["text"].splitlines()[0] == "EXIT GATE 4" and "Open 9 AM to 6 PM" in res.data["text"]
    assert not ocr.read(b"not an image").ok


@pytest.mark.skipif(not ocr.installed(), reason="rapidocr_onnxruntime not installed")
def test_chat_reads_text_from_attached_image_and_screen(monkeypatch, tmp_path):
    fresh_env()
    cid = context.new_conversation()
    r = engine.handle_message("read the text in this image", cid, attachments=[("sign.png", SIGN.read_bytes())]).data
    assert r["intent"] == "ocr_read" and "EXIT GATE 4" in r["reply"]
    shot = tmp_path / "shot.png"
    shot.write_bytes(SIGN.read_bytes())
    monkeypatch.setattr(system, "screenshot", lambda ctx=None: Result.success({"path": str(shot)}))
    r = engine.handle_message("read the text on my screen", cid).data
    assert r["intent"] == "ocr_read" and r["reply"].startswith("Text in the screen") and "Open 9 AM" in r["reply"]
    r = engine.handle_message("read the text in this image", cid).data
    assert "Attach a photo" in r["reply"]
    assert db.query_one("SELECT COUNT(*) AS n FROM audit_log WHERE action='ocr_read'")["n"] == 2


def test_chat_describes_attached_photo(monkeypatch):
    fresh_env()
    monkeypatch.setattr(detector, "detect", lambda b, **k: [dict(d) for d in DETS])
    r = engine.handle_message("what is in this photo", context.new_conversation(), attachments=[("p.png", _png())]).data
    assert r["intent"] == "vision_detect" and r["reply"].startswith("I can see 2 people and 1 cup.") and "on the left" in r["reply"]


def test_named_objects_known_unknown_and_found(monkeypatch):
    fresh_env()
    monkeypatch.setattr(detector, "detect", lambda b, **k: [dict(d) for d in DETS])
    monkeypatch.setattr(detector, "detect_open_vocab", lambda b, names, **k: [{"error": "YOLO-World could not be loaded"}])
    cid = context.new_conversation()
    r = engine.handle_message("is there a cup in this image", cid, attachments=[("p.png", _png())]).data
    assert "Yes, I can see a cup." in r["reply"]
    r = engine.handle_message("find a stapler and a laptop in the photo", cid, attachments=[("p.png", _png())]).data
    assert "cannot look for 'stapler'" in r["reply"] and "I do not see a laptop." in r["reply"]
    seen = {}
    monkeypatch.setattr(detector, "world_available", lambda: True)  # pretend YOLO-World is installed
    monkeypatch.setattr(detector, "detect_open_vocab", lambda b, names, **k: seen.setdefault("names", names) and
                        [{"label": "stapler", "confidence": 0.6, "box": [10, 10, 60, 40]}])
    r = engine.handle_message("find a stapler in the photo", cid, attachments=[("p.png", _png())]).data
    assert seen["names"] == ["stapler"] and "Yes, I can see a stapler." in r["reply"]


def test_small_objects_use_tiles_and_nothing_found_uses_classifier(monkeypatch):
    fresh_env()
    called = {}
    monkeypatch.setattr(detector, "detect_tiled", lambda b, **k: called.setdefault("tiled", True) and [dict(DETS[2])])
    r = engine.handle_message("look for small objects in this photo", context.new_conversation(), attachments=[("p.png", _png())]).data
    assert called.get("tiled") and "Scanned in tiles" in r["reply"]
    monkeypatch.setattr(detector, "detect", lambda b, **k: [])
    monkeypatch.setattr(detector, "classify", lambda b, **k: [{"label": "envelope", "confidence": 0.41}])
    r = engine.handle_message("what is this", context.new_conversation(), attachments=[("p.png", _png())]).data
    assert "Best guess for the whole picture: envelope (41%)" in r["reply"]


def test_chat_never_downloads_open_vocabulary_model(monkeypatch):
    fresh_env()  # empty models folder: YOLO-World is not installed
    monkeypatch.setattr(detector, "detect", lambda b, **k: [dict(d) for d in DETS])
    monkeypatch.setattr(detector, "detect_open_vocab", lambda *a, **k: (_ for _ in ()).throw(AssertionError("would download")))
    assert not detector.world_available() and os.environ.get("YOLO_AUTOINSTALL") == "false"
    r = engine.handle_message("find a stapler in the photo", context.new_conversation(), attachments=[("p.png", _png())]).data
    assert "cannot look for 'stapler'" in r["reply"]


def test_requested_names():
    assert features.requested_names("find a mug and a stapler in the photo") == ["mug", "stapler"]
    assert features.requested_names("do you see any bottles") == ["bottles"]
    assert features.requested_names("what is in this photo") == []

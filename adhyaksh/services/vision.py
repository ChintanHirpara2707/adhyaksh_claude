"""Service layer for the Object Detection page: the only adhyaksh functions that page may call.

Pages import nothing from adhyaksh except services and ui (tests/test_engineering.py checks this), so
the tools, models and storage behind a page can change without touching the page.
"""
from __future__ import annotations

from adhyaksh import config
from adhyaksh.vision import descriptions, detector, ocr, scene

# adhyaksh.config
get = config.get

# adhyaksh.vision.descriptions
descriptions_describe = descriptions.describe
descriptions_wikipedia = descriptions.wikipedia

# adhyaksh.vision.detector
DETECTION_MODELS = detector.DETECTION_MODELS
detector_average_brightness = detector.average_brightness
detector_classify = detector.classify
detector_detect = detector.detect
detector_detect_open_vocab = detector.detect_open_vocab
detector_detect_raw = detector.detect_raw
detector_detect_tiled = detector.detect_tiled
detector_parse_classes = detector.parse_classes

# adhyaksh.vision.ocr
ocr_read = ocr.read

# adhyaksh.vision.scene
scene_describe = scene.describe

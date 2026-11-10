"""Object Detection page: camera snapshot or uploaded image, YOLOv8n detection."""
from __future__ import annotations

import io
import streamlit as st
from PIL import Image, ImageDraw

from adhyaksh import config
from adhyaksh.ui import components as ui, theme
from adhyaksh.vision import detector, descriptions

ui.page_header("Object Detection", "Detect objects in a camera snapshot or uploaded image.")
theme.inject(config.get("theme") or "light")

conf = st.slider("Confidence threshold", 0.10, 0.80, 0.25, 0.05)

tab_camera, tab_upload = st.tabs(["Camera", "Upload image"])

if "vision" not in st.session_state:
    st.session_state["vision"] = {}
state = st.session_state["vision"]

image = None
active = None
with tab_camera:
    active = "camera"
    image = st.camera_input("Take a snapshot")
with tab_upload:
    active = "upload"
    image = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png", "webp"])

cur = state.setdefault(active, {"bytes": None, "detections": None})
if image is not None:
    b = image.getvalue()
    if cur.get("bytes") != b:
        detections = detector.detect(b, conf=conf)
        state[active] = {"bytes": b, "detections": detections}
    else:
        detections = cur.get("detections")
else:
    state[active] = {"bytes": None, "detections": None}
    detections = None

if image is None or not detections:
    st.info("No objects found. Try better light, or move the camera closer to the object.")
else:
    error = [d for d in detections if "error" in d]
    if error:
        st.error(error[0]["error"])
    else:
        img = Image.open(io.BytesIO(state[active]["bytes"])).convert("RGB")
        draw = ImageDraw.Draw(img)
        for d in detections:
            x1, y1, x2, y2 = d["box"]
            draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
            draw.text((x1, max(0, y1 - 14)), f'{d["label"]} {d["confidence"]:.0%}', fill="red")
        st.image(img, caption="Detected objects", use_container_width=True)

        grouped: dict[str, list[dict]] = {}
        for d in detections:
            grouped.setdefault(d["label"], []).append(d)
        for label, items in grouped.items():
            best = max(items, key=lambda x: x["confidence"])
            wiki = descriptions.wikipedia(label)
            st.markdown(
                f"**{label}** — {len(items)} found, best confidence {best['confidence']:.0%}.\n"
                f"{descriptions.describe(label)}{wiki}"
            )

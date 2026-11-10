"""Object Detection page: camera snapshot or uploaded image, YOLOv8n detection."""
from __future__ import annotations

import streamlit as st
from PIL import Image, ImageDraw

from adhyaksh.ui import components as ui, icons, theme
from adhyaksh.vision import detector, descriptions

ui.page_header("Object Detection", "Detect objects in a camera snapshot or uploaded image.")
theme.inject(theme.sidebar_header(key_suffix="vision"))
tab_camera, tab_upload = st.tabs(["Camera", "Upload image"])

image = None
with tab_camera:
    image = st.camera_input("Take a snapshot")
with tab_upload:
    image = st.file_uploader("Choose an image", type=["jpg", "jpeg", "png", "webp"])

if image is not None:
    img = Image.open(image).convert("RGB")
    img_bytes = image.getvalue()
    detections = detector.detect(img_bytes)

    error = [d for d in detections if "error" in d]
    if error:
        st.error(error[0]["error"])
    else:
        draw = ImageDraw.Draw(img)
        for d in detections:
            x1, y1, x2, y2 = d["box"]
            draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
            draw.text((x1, max(0, y1 - 14)), f'{d["label"]} {d["confidence"]:.2f}', fill="red")
        st.image(img, caption="Detected objects", use_container_width=True)

        if not detections:
            st.info("No objects found.")
        else:
            grouped: dict[str, list[dict]] = {}
            for d in detections:
                grouped.setdefault(d["label"], []).append(d)
            for label, items in grouped.items():
                best = max(items, key=lambda x: x["confidence"])
                st.markdown(
                    f"**{label}** — {len(items)} found, best confidence {best['confidence']:.2f}. "
                    f"{descriptions.describe(label)}"
                )
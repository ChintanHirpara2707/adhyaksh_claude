"""Object Detection page: camera snapshot or uploaded image, YOLOv8n detection."""
from __future__ import annotations

import hashlib
import io
import streamlit as st
from PIL import Image, ImageDraw

from adhyaksh import config
from adhyaksh.ui import components as ui, theme
from adhyaksh.vision import detector, descriptions

ui.page_header("Object Detection", "Detect objects in a camera snapshot or uploaded image.")
theme.inject(config.get("theme") or "light")

MODEL_CHOICES = {"fast": "Fast (yolov8n)", "balanced": "Balanced (yolov8s)", "accurate": "Accurate (yolov8m)"}

col_model, col_imgsz = st.columns(2)
with col_model:
    model_choice = st.selectbox("Detection model", list(MODEL_CHOICES),
                                format_func=lambda k: MODEL_CHOICES[k],
                                index=list(MODEL_CHOICES).index(config.get("vision_model") or "balanced"))
with col_imgsz:
    imgsz = st.selectbox("Image size", [640, 960],
                         index=[640, 960].index(int(config.get("vision_imgsz") or "640")))

conf = st.slider("Confidence threshold", 0.10, 0.80, 0.25, 0.05)

MODES = {
    "standard": "Standard (80 everyday object types)",
    "tiled": "Small objects (scans the image in tiles, slower)",
    "open": "Any object I name (YOLO-World, needs a one-time download)",
}
mode = st.radio("Detection mode", list(MODES), format_func=lambda k: MODES[k], horizontal=False)
open_classes: list[str] = []
if mode == "open":
    typed = st.text_input("Objects to look for, separated by commas",
                          placeholder="mug, stapler, red pen, houseplant", max_chars=300)
    open_classes = detector.parse_classes(typed)
    st.caption("Open-vocabulary detection is less reliable than the standard detector. "
               f"It needs about 400 MB of one-time downloads (YOLO-World weights and the CLIP text encoder).")
also_named = st.checkbox("Also name other things in the picture (1000 general categories)", value=False)

tab_camera, tab_upload = st.tabs(["Camera", "Upload image"])

if "vision" not in st.session_state:
    st.session_state["vision"] = {}
state = st.session_state["vision"]


def _cache_key(image_bytes: bytes) -> str:
    return hashlib.sha1(image_bytes).hexdigest()


def render(key: str, file) -> None:
    """Render one input source: detect, draw, descriptions, Closest match, Details."""
    detections = None
    image_bytes = None
    if file is not None:
        image_bytes = file.getvalue()

    ck = state.get(key)
    if image_bytes is not None:
        new_key = f"{_cache_key(image_bytes)}:{conf}:{imgsz}:{model_choice}:{mode}:{'|'.join(open_classes)}"
        if ck is None or ck.get("key") != new_key:
            if mode == "tiled":
                detections = detector.detect_tiled(image_bytes, conf=conf, imgsz=imgsz, model_choice=model_choice)
            elif mode == "open":
                detections = detector.detect_open_vocab(image_bytes, open_classes, conf=min(conf, 0.3), imgsz=imgsz)
            else:
                detections = detector.detect(image_bytes, conf=conf, imgsz=imgsz, model_choice=model_choice)
            state[key] = {"key": new_key, "bytes": image_bytes, "detections": detections}
        else:
            detections = ck.get("detections")
            image_bytes = ck.get("bytes")
    else:
        state[key] = None

    if image_bytes is None or detections is None:
        return

    error = [d for d in detections if "error" in d]
    if error:
        st.error(error[0]["error"])
        return

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(img)
    for d in detections:
        x1, y1, x2, y2 = d["box"]
        draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
        draw.text((x1, max(0, y1 - 14)), f'{d["label"]} {d["confidence"]:.0%}', fill="red")
    st.image(img, caption="Detected objects", use_container_width=True)

    if not detections:
        st.info("No objects found. Try better light, or move the camera closer to the object.")
        # Classifier fallback when detection found nothing
        fallback = detector.classify(image_bytes, imgsz=imgsz)
        if isinstance(fallback, str):
            st.info(fallback)
        elif fallback:
            st.markdown("**Closest match** — best guess for the main object in the image:")
            for g in fallback[:3]:
                wiki = descriptions.wikipedia(g["label"])
                st.markdown(
                    f"**{g['label']}** — {g['confidence']:.0%}.\n"
                    f"{descriptions.describe(g['label'])}{wiki}"
                )
        return

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

    if also_named:
        named = detector.classify(image_bytes, imgsz=imgsz)
        if isinstance(named, str):
            st.info(named)
        elif named:
            st.markdown("**Other things this picture may show** (general categories, whole image):")
            st.markdown("\n".join(f"- {g['label']} - {g['confidence']:.0%}" for g in named[:5]))

    # Collapsible Details section
    w, h = img.size
    bright = detector.average_brightness(image_bytes)
    raw = detector.detect_raw(image_bytes, model_choice=model_choice)
    camera_bytes = len(image_bytes) if key == "camera" else None
    model_name = detector.DETECTION_MODELS.get(model_choice, model_choice)
    with st.expander("Details", expanded=False):
        st.markdown(f"- Size: {w} × {h} pixels")
        st.markdown(f"- File size: {len(image_bytes)} bytes")
        if bright is not None:
            st.markdown(f"- Average brightness: {bright:.0f} / 255")
        else:
            st.markdown("- Average brightness: unreadable")
        st.markdown(f"- Model: {model_name} ({MODES[mode]})")
        st.markdown(f"- Confidence threshold: {conf:.0%}")
        if camera_bytes is not None:
            st.markdown(f"- Camera bytes read: {camera_bytes}")
        st.markdown("**Raw detections (confidence ≥ 0.05, top 5):**")
        if raw:
            for d in raw:
                st.markdown(f"  - {d['label']} — {d['confidence']:.0%}")
        else:
            st.markdown("  - none")


with tab_camera:
    render("camera", st.camera_input("Take a snapshot"))

with tab_upload:
    render("upload", st.file_uploader("Choose an image", type=["jpg", "jpeg", "png", "webp"]))

if state.get("camera") is None and state.get("upload") is None:
    st.info("Take a snapshot or upload an image.")

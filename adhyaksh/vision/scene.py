"""Richer descriptions of what the detector found: counts, positions, sizes and approximate colours.

Works on the detector's boxes and the image pixels only; no extra model. Colours are approximate (the average
colour of the middle of each box, named from a small palette).
"""
from __future__ import annotations

import io
from collections import Counter

PALETTE = {"black": (25, 25, 25), "white": (240, 240, 240), "grey": (128, 128, 128), "red": (200, 30, 40),
           "orange": (240, 140, 30), "yellow": (235, 215, 40), "green": (50, 160, 60), "blue": (40, 90, 200),
           "light blue": (130, 190, 235), "purple": (120, 60, 160), "pink": (235, 130, 180), "brown": (130, 80, 40),
           "beige": (215, 195, 160)}
PLURAL = {"person": "people", "mouse": "mice", "knife": "knives", "bus": "buses", "couch": "couches", "glass": "glasses",
          "sandwich": "sandwiches", "dish": "dishes", "wine glass": "wine glasses"}


def color_name(rgb) -> str:
    r, g, b = (float(x) for x in rgb[:3])
    best, dist = "grey", 1e9
    for name, (pr, pg, pb) in PALETTE.items():
        d = (r - pr) ** 2 * 0.3 + (g - pg) ** 2 * 0.59 + (b - pb) ** 2 * 0.11
        if d < dist:
            best, dist = name, d
    return best


def plural(label: str, n: int) -> str:
    if n == 1:
        return label
    return PLURAL.get(label, label + "s")


def position(box, w: int, h: int) -> str:
    cx, cy = (box[0] + box[2]) / 2 / max(w, 1), (box[1] + box[3]) / 2 / max(h, 1)
    col = "left" if cx < 0.36 else "right" if cx > 0.64 else "centre"
    row = "top" if cy < 0.33 else "bottom" if cy > 0.67 else ""
    if col == "centre" and not row:
        return "in the centre"
    if col == "centre":
        return f"at the {row}"
    return f"at the {row} {col}".replace("the  ", "the ") if row else f"on the {col}"


def size_word(box, w: int, h: int) -> str:
    share = max(0.0, (box[2] - box[0]) * (box[3] - box[1])) / max(1, w * h)
    return "large" if share > 0.25 else "small" if share < 0.05 else "medium-sized"


def _box_color(img, box) -> str:
    import numpy as np
    x0, y0, x1, y1 = (int(v) for v in box)
    dx, dy = (x1 - x0) // 4, (y1 - y0) // 4
    crop = np.asarray(img.crop((x0 + dx, y0 + dy, max(x0 + dx + 1, x1 - dx), max(y0 + dy + 1, y1 - dy))).convert("RGB"))
    if crop.size == 0:
        return "grey"
    return color_name(crop.reshape(-1, 3).mean(axis=0))


def describe(image_bytes: bytes, detections: list[dict], max_items: int = 6) -> dict:
    """{summary, items: [{label, count, position, size, color, confidence}], image: {brightness, color}}."""
    import numpy as np
    from PIL import Image
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:  # unreadable pixels: describe from the boxes alone
        img = None
    if img is not None:
        w, h = img.size
        arr = np.asarray(img.resize((64, 64)))
        bright = float(arr.mean())
        overall = {"brightness": "dark" if bright < 70 else "bright" if bright > 185 else "normal",
                   "color": color_name(arr.reshape(-1, 3).mean(axis=0))}
    else:
        w = int(max([d["box"][2] for d in detections if "box" in d] or [1]))
        h = int(max([d["box"][3] for d in detections if "box" in d] or [1]))
        overall = {"brightness": "normal", "color": "unknown"}
    dets = sorted([d for d in detections if "box" in d], key=lambda d: d["confidence"], reverse=True)
    counts = Counter(d["label"] for d in dets)
    items, seen = [], set()
    for d in dets:
        if d["label"] in seen:
            continue
        seen.add(d["label"])
        biggest = max((x for x in dets if x["label"] == d["label"]), key=lambda x: (x["box"][2] - x["box"][0]) * (x["box"][3] - x["box"][1]))
        items.append({"label": d["label"], "count": counts[d["label"]], "position": position(biggest["box"], w, h),
                      "size": size_word(biggest["box"], w, h), "color": _box_color(img, biggest["box"]) if img is not None else "unknown",
                      "confidence": round(max(x["confidence"] for x in dets if x["label"] == d["label"]), 2)})
        if len(items) >= max_items:
            break
    if not items:
        summary = f"I could not recognise any of the objects I know. The picture is {overall['brightness']} and mostly {overall['color']}."
    else:
        parts = [f"{c} {plural(lbl, c)}" for lbl, c in counts.most_common()]
        listing = parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + " and " + parts[-1]
        details = []
        for it in items:
            noun = f"the {it['label']}" if it["count"] == 1 else f"the largest {it['label']}"
            colour = f", mostly {it['color']}" if it["color"] != "unknown" else ""
            details.append(f"{noun[0].upper()}{noun[1:]} is {it['position']}, {it['size']}{colour}.")
        summary = f"I can see {listing}. " + " ".join(details)
        if overall["brightness"] == "dark":
            summary += " The photo is quite dark, so small or dark objects may be missed."
    return {"summary": summary, "items": items, "image": overall, "total": len(dets)}

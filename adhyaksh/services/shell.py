"""Service layer for the app shell (app.py): navigation groups, the sidebar status line and due reminders."""
from __future__ import annotations

from adhyaksh import config

# Sidebar sections, in order. Every page appears exactly once (tests/test_ui_polish.py checks this).
NAV: list[tuple[str, list[tuple[str, str]]]] = [
    ("Assistant", [("chat", "Chat"), ("memory", "Memory")]),
    ("Tools", [("tools", "Tools"), ("vision", "Object Detection"), ("performance", "PC Performance")]),
    ("System", [("model_lab", "Model Lab"), ("activity", "Activity"), ("health", "Health"), ("settings", "Settings")]),
]


def pages() -> list[tuple[str, str]]:
    return [p for _, group in NAV for p in group]


def status() -> list[str]:
    """Short lines for the bottom of the sidebar: where answers come from and whether anything may leave the PC."""
    from adhyaksh.llm import base as llm
    from adhyaksh.nlu import registry

    lines = []
    provider = config.get("llm_provider")
    consent = config.get_bool("cloud_consent")
    if provider in llm.LOCAL_PROVIDERS:
        lines.append(f"Language model: {provider} (on this PC)")
    elif provider and consent and llm.api_key(provider):
        lines.append(f"Language model: {provider} (cloud)")
    else:
        lines.append("Language model: off (rules and local models)")
    lines.append("Cloud use: allowed" if consent else "Private mode: nothing leaves this PC")
    try:
        lines.append("Intent model: ready" if registry.available() else "Intent model: not trained")
    except Exception:
        lines.append("Intent model: could not load")
    return lines


def due_reminders() -> list[dict]:
    from adhyaksh.tools import reminders
    return reminders.due()

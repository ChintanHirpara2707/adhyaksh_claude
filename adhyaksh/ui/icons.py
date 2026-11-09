"""Navigation icons (Streamlit Material Symbols; simple line style, no emoji)."""
PAGE_ICONS = {
    "chat": ":material/chat_bubble:",
    "documents": ":material/description:",
    "memory": ":material/psychology:",
    "tools": ":material/build:",
    "model_lab": ":material/science:",
    "activity": ":material/history:",
    "settings": ":material/settings:",
    "vision": ":material/camera:",
}


def page_icon(slug: str) -> str:
    return PAGE_ICONS[slug]

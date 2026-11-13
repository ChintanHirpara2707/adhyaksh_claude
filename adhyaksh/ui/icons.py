"""Navigation icons (Streamlit Material Symbols; simple line style, no emoji)."""
PAGE_ICONS = {
    "chat": ":material/chat_bubble:",
    "memory": ":material/psychology:",
    "tools": ":material/build:",
    "model_lab": ":material/science:",
    "activity": ":material/history:",
    "settings": ":material/settings:",
    "vision": ":material/camera:",
    "performance": ":material/speed:",
}



def page_icon(slug: str) -> str:
    return PAGE_ICONS[slug]

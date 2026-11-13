"""ADHYAKSH entry point: page routing only."""
import streamlit as st

from adhyaksh import db, logging_setup
from adhyaksh.ui import icons, theme

st.set_page_config(page_title="ADHYAKSH", layout="wide")


@st.cache_resource
def _boot() -> bool:
    logging_setup.setup()
    db.init()
    return True


_boot()

PAGES = [("chat", "Chat"), ("memory", "Memory"), ("tools", "Tools"),
         ("model_lab", "Model Lab"), ("activity", "Activity"), ("settings", "Settings"),
         ("vision", "Object Detection"), ("performance", "PC Performance")]
pages = [
    st.Page(f"pages/{slug}.py", title=title, icon=icons.page_icon(slug), url_path=slug,
            default=(slug == "chat"))
    for slug, title in PAGES
]
current = st.navigation(pages, position="hidden")
saved_theme = theme.sidebar_header()
theme.inject(saved_theme)
for page in pages:
    st.sidebar.page_link(page)
current.run()

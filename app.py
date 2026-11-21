"""ADHYAKSH entry point: page routing only."""
import streamlit as st

from adhyaksh import db, logging_setup
from adhyaksh.services import shell
from adhyaksh.ui import icons, theme

st.set_page_config(page_title="ADHYAKSH", layout="wide")


@st.cache_resource
def _boot() -> bool:
    logging_setup.setup()
    db.init()
    return True


_boot()

PAGES = shell.pages()
pages = {
    slug: st.Page(f"app_pages/{slug}.py", title=title, icon=icons.page_icon(slug), url_path=slug,
                  default=(slug == "chat"))
    for slug, title in PAGES
}
current = st.navigation(list(pages.values()), position="hidden")
saved_theme = theme.sidebar_header()
theme.inject(saved_theme, ["/"] + [f"/{slug}" for slug, _ in PAGES])
for section, group in shell.NAV:
    st.sidebar.markdown(f'<p class="adhy-nav-section">{section}</p>', unsafe_allow_html=True)
    for slug, _ in group:
        st.sidebar.page_link(pages[slug])
# A page's own sidebar part (the Chat page's conversations) goes here: after the links, above the status line.
st.session_state["page_sidebar"] = st.sidebar.container()


@st.fragment(run_every=20)
def _reminder_alerts() -> None:
    """Show reminders that are due (while the app is open in a browser)."""
    for r in shell.due_reminders():
        st.toast(f"Reminder: {r['text']}")
        st.sidebar.warning(f"Reminder: {r['text']}")


with st.sidebar:
    _reminder_alerts()
    st.markdown('<div class="adhy-status">' + "<br>".join(shell.status()) + "</div>", unsafe_allow_html=True)
current.run()

"""Design tokens and CSS. Colors are defined once here as CSS variables; nowhere else."""
from __future__ import annotations

TOKENS: dict[str, dict[str, str]] = {
    "light": {
        "bg": "#FAF9F5", "surface": "#FFFFFF", "subtle": "#F3F1EA", "border": "#E8E5DC",
        "text": "#1F1E1D", "muted": "#6B6860", "accent": "#C96442", "accent_strong": "#A8502F",
        "on_accent": "#FFFFFF", "success": "#2F6B3F", "warning": "#8A5A00", "error": "#A83232",
    },
    "dark": {
        "bg": "#262624", "surface": "#30302E", "subtle": "#3A3936", "border": "#44433F",
        "text": "#F5F4EE", "muted": "#A8A59B", "accent": "#C96442", "accent_strong": "#A8502F",
        "on_accent": "#FFFFFF", "success": "#7DBE8C", "warning": "#D9A441", "error": "#F0A0A0",
    },
}

FONT_UI = ('Inter, system-ui, "Segoe UI", "Noto Sans Devanagari", "Noto Sans Gujarati", '
           '"Nirmala UI", sans-serif')
FONT_SERIF = 'Georgia, "Source Serif 4", "Noto Serif Devanagari", "Noto Serif Gujarati", serif'
FONT_MONO = 'ui-monospace, "Cascadia Mono", Consolas, monospace'


def resolve(theme: str) -> dict[str, str]:
    return TOKENS[theme if theme in TOKENS else "light"]


def _vars(name: str) -> str:
    body = ";".join(f"--{k.replace('_', '-')}:{v}" for k, v in TOKENS[name].items())
    return body + f";color-scheme:{name}"


def build_css(theme: str) -> str:
    """theme: 'light', 'dark', or '' (never chosen: light, but follow the OS preference)."""
    if theme in ("light", "dark"):
        root = f":root{{{_vars(theme)}}}"
    else:
        root = f":root{{{_vars('light')}}}@media (prefers-color-scheme: dark){{:root{{{_vars('dark')}}}}}"
    return f"<style>{root}{_STATIC}</style>"


_STATIC = f"""
:root{{--font-ui:{FONT_UI};--font-serif:{FONT_SERIF};--font-mono:{FONT_MONO};--radius:10px}}
html,body,[data-testid="stApp"]{{background:var(--bg);color:var(--text);font-family:var(--font-ui);
 font-size:15.5px;line-height:1.6;transition:background-color .18s,color .18s,border-color .18s}}
[data-testid="stHeader"]{{background:var(--bg)}}
footer,#MainMenu{{visibility:hidden}}
[data-testid="stMainBlockContainer"]{{max-width:1000px;padding-top:2.5rem}}
.stApp p,.stApp li,.stApp label,.stApp span,.stApp div[data-testid="stMarkdownContainer"],
.stApp h1,.stApp h2,.stApp h3,.stApp h4{{color:var(--text)}}
.stApp h1,.stApp h2,.stApp h3{{font-family:var(--font-serif);font-weight:500;letter-spacing:0}}
.stApp code,.stApp pre{{font-family:var(--font-mono);background:var(--subtle);color:var(--text)}}
[data-testid="stCaptionContainer"],.adhy-muted{{color:var(--muted)!important}}
*:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}}
[data-testid="stSidebar"]{{background:var(--subtle);border-right:1px solid var(--border)}}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]{{border-radius:var(--radius);padding:.35rem .6rem}}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"]:hover{{background:var(--border)}}
[data-testid="stSidebar"] [data-testid="stPageLink-NavLink"][aria-current="page"]{{
 background:var(--surface);border-left:3px solid var(--accent)}}
.adhy-brand{{font-family:var(--font-serif);font-size:1.25rem;letter-spacing:.08em;margin:0 0 .5rem 0}}
.adhy-header{{border-bottom:1px solid var(--border);margin-bottom:1.5rem;padding-bottom:.75rem}}
.adhy-header h1{{margin:0;font-size:1.75rem}}
.adhy-header p{{margin:.25rem 0 0 0}}
.adhy-card{{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
 padding:1rem 1.25rem;margin:.5rem 0}}
.adhy-card p{{margin:0}}
input,textarea,[data-baseweb="input"],[data-baseweb="textarea"],[data-baseweb="select"]>div{{
 background:var(--surface)!important;color:var(--text)!important;border-color:var(--border)!important;
 border-radius:var(--radius)}}
[data-baseweb="popover"],[data-baseweb="menu"],ul[role="listbox"]{{background:var(--surface)!important;
 color:var(--text)!important;border:1px solid var(--border)}}
.stButton>button,.stDownloadButton>button{{background:var(--surface);color:var(--text);
 border:1px solid var(--border);border-radius:var(--radius);box-shadow:none}}
.stButton>button:hover,.stDownloadButton>button:hover{{background:var(--subtle);border-color:var(--muted)}}
[data-testid="stBaseButton-primary"]{{background:var(--accent-strong);color:var(--on-accent);
 border:1px solid var(--accent-strong)}}
[data-testid="stBaseButton-primary"] *{{color:var(--on-accent)!important}}
button[data-baseweb="tab"]{{color:var(--muted)}}
button[data-baseweb="tab"][aria-selected="true"]{{color:var(--text)}}
[data-baseweb="tab-highlight"]{{background:var(--text)}}
[data-baseweb="tab-border"]{{background:var(--border)}}
[data-testid="stExpander"] details{{background:var(--surface);border:1px solid var(--border);
 border-radius:var(--radius)}}
[data-testid="stFileUploaderDropzone"]{{background:var(--surface);border:1px dashed var(--border);
 border-radius:var(--radius)}}
[data-testid="stAlert"]{{background:var(--surface);border:1px solid var(--border);
 border-radius:var(--radius);color:var(--text)}}
[data-testid="stToast"]{{background:var(--surface);color:var(--text);border:1px solid var(--border)}}
[data-testid="stTable"] table{{border-collapse:collapse;width:100%}}
[data-testid="stTable"] th{{background:var(--subtle);color:var(--text);border-bottom:1px solid var(--border);
 position:sticky;top:0}}
[data-testid="stTable"] td{{border-bottom:1px solid var(--border);color:var(--text)}}
[data-testid="stProgress"] div[role="progressbar"]{{height:4px;background:var(--border)}}
[data-testid="stChatMessage"]{{background:transparent}}
[data-testid="stChatMessage"]:has([data-testid="stChatMessageAvatarUser"]){{
 background:var(--subtle);border-radius:var(--radius)}}
[data-testid="stBottom"]>div,[data-testid="stChatInput"]{{background:var(--bg)}}
[data-testid="stChatInput"] textarea{{background:var(--surface)!important}}
"""


def sidebar_header() -> str:
    """Brand and Light/Dark switch at the top of the sidebar. Returns the saved theme."""
    import streamlit as st

    from adhyaksh import config

    saved = config.get("theme")
    if "theme_toggle" not in st.session_state:
        st.session_state["theme_toggle"] = saved == "dark"
    with st.sidebar:
        st.markdown('<p class="adhy-brand">ADHYAKSH</p>', unsafe_allow_html=True)
        is_dark = st.toggle("Dark mode", key="theme_toggle")
    chosen = "dark" if is_dark else "light"
    if is_dark != (saved == "dark"):
        config.set_value("theme", chosen)
        saved = chosen
    return saved


def inject(theme: str) -> None:
    import streamlit as st

    st.markdown(build_css(theme), unsafe_allow_html=True)

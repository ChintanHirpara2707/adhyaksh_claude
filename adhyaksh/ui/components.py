"""Reusable UI pieces following the design system. Pages call these; no logic lives in pages."""
from __future__ import annotations

import html

import streamlit as st


def page_header(title: str, description: str) -> None:
    st.markdown(
        f'<div class="adhy-header"><h1>{html.escape(title)}</h1>'
        f'<p class="adhy-muted">{html.escape(description)}</p></div>',
        unsafe_allow_html=True,
    )


def chat_welcome(title: str, subtitle: str) -> None:
    """The empty-conversation greeting: a large serif line and one muted line, centred."""
    st.markdown(
        f'<div class="adhy-welcome"><h2>{html.escape(title)}</h2><p class="adhy-muted">{html.escape(subtitle)}</p></div>'
        '<style>.adhy-welcome{text-align:center;padding:12vh 0 1.2rem}.adhy-welcome h2{font-size:2rem;margin:0 0 .4rem}</style>',
        unsafe_allow_html=True,
    )


def empty_state(message: str) -> None:
    st.markdown(f'<div class="adhy-card"><p>{html.escape(message)}</p></div>', unsafe_allow_html=True)


def error_state(message: str, reason: str, next_step: str) -> None:
    st.error(f"{message} Reason: {reason}. Next step: {next_step}")


def human_size(n: int | float | None) -> str:
    """Bytes as a short readable size: 512 B, 3.4 KB, 12.0 MB, 1.2 GB."""
    if n is None:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{int(n)} B" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


def wide(px: int = 1240) -> None:
    """Wider main column for pages that are mostly tables and charts."""
    chat_width(px)


def chat_width(px: int = 820) -> None:
    st.markdown(
        f'<style>[data-testid="stMainBlockContainer"],[data-testid="stBottomBlockContainer"]{{max-width:{int(px)}px}}</style>',
        unsafe_allow_html=True,
    )


ORB = {  # one hue per state, readable from across the room; calm motion, no flashing
    "idle": ("#5b8a98", "Ready", "none"),
    "listening": ("#2bb6e0", "Listening", "adhy-breathe 1.6s ease-in-out infinite"),
    "thinking": ("#e0a030", "Thinking", "adhy-spin 1.4s linear infinite"),
    "speaking": ("#3cbf74", "Speaking", "adhy-breathe 0.9s ease-in-out infinite"),
    "executing": ("#5b7cf0", "Working", "adhy-spin 0.8s linear infinite"),
}


def orb_html(state: str, detail: str = "") -> str:
    """A large microphone orb for the Voice page. Pure CSS (no script); colour and motion follow the state."""
    color, label, motion = ORB.get(state, ORB["idle"])
    detail = html.escape(detail)[:80]
    return f"""
<style>
@keyframes adhy-breathe {{0%,100% {{transform:scale(1);opacity:.85}} 50% {{transform:scale(1.07);opacity:1}}}}
@keyframes adhy-spin {{to {{transform:rotate(360deg)}}}}
.adhy-orb-wrap {{display:flex;flex-direction:column;align-items:center;gap:.7rem;padding:1.2rem 0 .4rem}}
.adhy-orb {{position:relative;width:190px;height:190px;border-radius:50%;display:flex;align-items:center;justify-content:center;
  background:radial-gradient(circle at 50% 42%, {color}33 0%, {color}14 55%, transparent 72%)}}
.adhy-orb-ring {{position:absolute;inset:8px;border-radius:50%;border:6px solid {color};
  border-top-color:{color}{'55' if 'spin' in motion else ''};animation:{motion}}}
.adhy-orb-core {{width:96px;height:96px;border-radius:50%;background:{color};opacity:.92;display:flex;align-items:center;
  justify-content:center;color:#fff;font-weight:600;letter-spacing:.02em;font-size:.95rem}}
.adhy-orb-label {{font-size:1.05rem;color:var(--text, inherit);opacity:.85}}
.adhy-orb-detail {{font-size:.85rem;opacity:.6;min-height:1.1em}}
</style>
<div class="adhy-orb-wrap" role="status" aria-live="polite" aria-label="Assistant state: {label}">
  <div class="adhy-orb"><div class="adhy-orb-ring"></div><div class="adhy-orb-core">{label}</div></div>
  <div class="adhy-orb-detail">{detail}</div>
</div>"""


def confirmation_card(action: str, target: str, key: str) -> str | None:
    """Two-step confirmation card. Returns 'confirm', 'cancel' or None."""
    with st.container(border=True):
        st.markdown(f"**{html.escape(action)}**")
        st.code(target, language=None)
        left, right = st.columns(2)
        if left.button("Confirm", type="primary", key=f"{key}_confirm"):
            return "confirm"
        if right.button("Cancel", key=f"{key}_cancel"):
            return "cancel"
    return None


def first_run_form() -> None:
    """Journey J1: ask for the operator name and the allowed workspace folder."""
    from adhyaksh import config
    from adhyaksh.chat import identity

    st.markdown("Welcome. Enter your name and choose the folder the assistant may work in.")
    with st.form("first_run"):
        name = st.text_input("Your name", max_chars=60)
        folder = st.text_input("Allowed workspace folder", value=str(config.default_workspace()))
        if st.form_submit_button("Save and continue", type="primary"):
            if not name.strip():
                st.error("Enter your name to continue.")
            else:
                ok, msg = config.configure_folders([folder], folder)
                if ok:
                    identity.save_name(name.strip())
                    st.rerun()
                else:
                    st.error(msg)

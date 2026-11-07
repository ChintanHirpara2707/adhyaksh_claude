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


def empty_state(message: str) -> None:
    st.markdown(f'<div class="adhy-card"><p>{html.escape(message)}</p></div>', unsafe_allow_html=True)


def error_state(message: str, reason: str, next_step: str) -> None:
    st.error(f"{message} Reason: {reason}. Next step: {next_step}")


def chat_width(px: int = 820) -> None:
    st.markdown(
        f'<style>[data-testid="stMainBlockContainer"]{{max-width:{int(px)}px}}</style>',
        unsafe_allow_html=True,
    )


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

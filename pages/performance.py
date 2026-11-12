"""PC Performance page: live gauges and temp file cleanup."""
from __future__ import annotations

import streamlit as st

from adhyaksh import config
from adhyaksh.ui import components as ui, theme
from adhyaksh.tools import boost

ui.page_header("PC Performance", "CPU, RAM and disk stats, plus temp file cleanup.")
theme.inject(config.get("theme") or "light")


@st.fragment(run_every=3)
def _gauges():
    s = boost.stats()
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("CPU %", f"{s['cpu_percent']:.0f}")
        st.progress(min(int(s["cpu_percent"]), 100) / 100.0)
    with c2:
        st.metric("RAM %", f"{s['ram_percent']:.0f}", f"{s['ram_available_gb']:.1f} GB free")
        st.progress(min(int(s["ram_percent"]), 100) / 100.0)
    with c3:
        st.metric("Disk %", f"{s['disk_percent']:.0f}", f"{s['disk_free_gb']:.1f} GB free")
        st.progress(min(int(s["disk_percent"]), 100) / 100.0)
    with c4:
        temp = boost.scan_temp()
        mb = temp["bytes"] / (1024 * 1024)
        st.metric("Temp files MB", f"{mb:.1f}", f"{temp['files']} files")
        st.progress(min(int(mb / 100), 100) / 100.0)


_gauges()

st.subheader("Boost PC")

if "perf_scan" not in st.session_state:
    st.session_state["perf_scan"] = None

if st.button("Boost PC"):
    temp = boost.scan_temp()
    mb = temp["bytes"] / (1024 * 1024)
    st.session_state["perf_scan"] = {"files": temp["files"], "bytes": temp["bytes"], "mb": mb}

scan = st.session_state.get("perf_scan")
if scan is not None:
    st.info(f"Found {scan['mb']:.1f} MB in {scan['files']} files that can be removed.")
    c_clean, c_cancel = st.columns(2)
    with c_clean:
        if st.button("Clean now"):
            res = boost.clean_temp()
            freed_mb = res["freed_bytes"] / (1024 * 1024)
            st.success(f"Freed {freed_mb:.1f} MB. Skipped {res['skipped']} files in use.")
            st.session_state["perf_scan"] = None
            st.rerun()
    with c_cancel:
        if st.button("Cancel"):
            st.session_state["perf_scan"] = None
            st.rerun()

"""Health page: every dependency, model, setting and service, with its state and what to do next."""
from __future__ import annotations

import streamlit as st

from adhyaksh.services import health as svc
from adhyaksh.ui import components as ui

LABELS = {"ok": "OK", "optional": "Optional, not installed", "missing": "Missing", "problem": "Problem"}

ui.wide()
ui.page_header("Health", "What is installed and working. Nothing on this page downloads anything or sends data online.")

probe = st.checkbox("Check that Ollama is running (only if Ollama is the chosen provider)", value=True)
rows = svc.checks(probe_ollama=probe)
counts = svc.summary(rows)
c1, c2, c3, c4 = st.columns(4)
c1.metric("OK", counts["ok"])
c2.metric("Optional, not installed", counts["optional"])
c3.metric("Missing", counts["missing"])
c4.metric("Problems", counts["problem"])
if counts["missing"] or counts["problem"]:
    st.warning("Some parts need attention. See the rows marked Missing or Problem below.")
else:
    st.success("Everything required is installed and working.")

for area in dict.fromkeys(r["area"] for r in rows):
    st.subheader(area)
    st.dataframe([{"Name": r["name"], "State": LABELS[r["state"]], "Details": r["detail"]} for r in rows if r["area"] == area],
                 hide_index=True, width="stretch")

st.subheader("Recent warnings and errors")
log = svc.recent_log(30, "WARNING")
if not log:
    ui.empty_state("No warnings or errors in the log.")
else:
    st.dataframe([{"Time": r.get("ts", ""), "Level": r.get("level", ""), "Event": r.get("event", ""),
                   "Details": ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("ts", "level", "logger", "event", "error"))}
                  for r in log], hide_index=True, width="stretch")
    with st.expander("Full error details of the latest error"):
        latest = next((r for r in log if r.get("error")), None)
        st.code(latest["error"] if latest else "No error details recorded.")

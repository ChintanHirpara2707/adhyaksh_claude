import streamlit as st

from adhyaksh.safety import audit
from adhyaksh.ui import components as ui

ui.page_header("Activity", "Append-only record of every action the assistant performed or refused.")
rows = audit.list_recent(50)
if not rows:
    ui.empty_state("No actions recorded yet.")
else:
    st.table([{k: r[k] for k in ("ts", "action", "target", "level", "confirmed", "result")} for r in rows])

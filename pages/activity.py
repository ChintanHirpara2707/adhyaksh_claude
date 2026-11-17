import streamlit as st

from adhyaksh.services import activity as svc
from adhyaksh.ui import components as ui

ui.wide()
ui.page_header("Activity", "Append-only record of every action the assistant performed or refused.")
all_rows = svc.rows(500)
if not all_rows:
    ui.empty_state("No actions recorded yet.")
else:
    counts = svc.summary(all_rows)
    cols = st.columns(len(svc.OUTCOMES))
    for col, key in zip(cols, svc.OUTCOMES):
        col.metric(key.capitalize(), counts[key])
    left, right = st.columns([2, 3])
    picked = left.multiselect("Outcome", svc.OUTCOMES, placeholder="All outcomes")
    search = right.text_input("Search action, target or result", max_chars=100)
    shown = svc.filter_rows(all_rows, picked, search)
    st.caption(f"Showing {len(shown)} of {len(all_rows)} most recent actions.")
    if shown:
        st.dataframe(shown, hide_index=True, width="stretch",
                     column_config={"Result": st.column_config.TextColumn(width="large")})
        st.download_button("Download as CSV", data=svc.to_csv(shown), file_name="adhyaksh_activity.csv", mime="text/csv")
    else:
        ui.empty_state("No actions match these filters.")

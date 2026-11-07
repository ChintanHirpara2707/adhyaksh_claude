import streamlit as st

from adhyaksh.memory import store
from adhyaksh.ui import components as ui

ui.page_header("Memory", "Facts you asked the assistant to remember.")
with st.form("add_fact", clear_on_submit=True):
    new = st.text_input("Add a fact", placeholder="my car is Audi", max_chars=300)
    if st.form_submit_button("Save fact", type="primary") and new.strip():
        res = store.save_fact(new)
        st.toast("Already stored." if res.ok and res.data["duplicate"] else "Saved.")
        st.rerun()
query = st.text_input("Search facts", max_chars=100)
facts = store.list_facts(query or None)
if not facts:
    ui.empty_state("No facts stored. Add one above or tell the assistant: remember that my car is Audi.")
for f in facts:
    with st.expander(f"{f['fact']}"):
        st.caption(f"Category: {f['category']}. Updated: {f['updated_at']}")
        text = st.text_input("Edit", value=f["fact"], key=f"edit_{f['id']}", max_chars=300)
        left, right = st.columns(2)
        if left.button("Save changes", key=f"save_{f['id']}") and text.strip():
            store.update_fact(f["id"], text)
            st.rerun()
        if right.button("Delete", key=f"del_{f['id']}"):
            store.delete_fact(f["id"])
            st.rerun()

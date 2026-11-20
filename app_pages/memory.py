import streamlit as st

from adhyaksh.services import memory as svc
from adhyaksh.ui import components as ui

ui.page_header("Memory", "Facts you asked the assistant to remember. Saving the same kind of fact again updates it.")
auto = st.toggle("Remember personal facts I mention in passing (automatic memory)", value=svc.auto_memory_enabled(),
                 help="Off by default. When on, statements such as 'my exam is on Friday' are kept as 'automatic' facts. "
                      "They stay on this PC and never replace a fact you saved yourself.")
if auto != svc.auto_memory_enabled():
    svc.set_auto_memory(auto)
    st.toast("Automatic memory is " + ("on." if auto else "off."))
with st.form("add_fact", clear_on_submit=True):
    new = st.text_input("Add a fact", placeholder="my car is Audi", max_chars=300)
    if st.form_submit_button("Save fact", type="primary") and new.strip():
        res = svc.store_save_fact(new)
        st.toast("Already stored." if res.ok and res.data["duplicate"] else
                 "Updated the earlier fact." if res.ok and res.data.get("updated") else "Saved.")
        st.rerun()
query = st.text_input("Search facts", max_chars=100)
facts = svc.store_list_facts(query or None)
if not facts:
    ui.empty_state("No facts stored. Add one above or tell the assistant: remember that my car is Audi.")
for f in facts:
    label = f"{f['attribute']}: {f['value']}" if f.get("attribute") else f["fact"]
    with st.expander(label + ("  (automatic)" if f.get("source") == "auto" else "")):
        st.caption(f"Saved as: {f['fact']}. Source: {'noticed in conversation' if f.get('source') == 'auto' else 'you'}. "
                   f"Updated: {f['updated_at']}")
        text = st.text_input("Edit", value=f["fact"], key=f"edit_{f['id']}", max_chars=300)
        left, right = st.columns(2)
        if left.button("Save changes", key=f"save_{f['id']}") and text.strip():
            svc.store_update_fact(f["id"], text)
            st.rerun()
        if right.button("Delete", key=f"del_{f['id']}"):
            svc.store_delete_fact(f["id"])
            st.rerun()

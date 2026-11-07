import streamlit as st

from adhyaksh import config
from adhyaksh.result import E_NEEDS_CONFIRM
from adhyaksh.safety import policy
from adhyaksh.tools import apps, files, system
from adhyaksh.ui import components as ui

ui.page_header("Tools", "System status, workspace files and allowed applications. All actions are checked and logged.")
st.subheader("System status")
if st.button("Refresh status") or "status_loaded" not in st.session_state:
    st.session_state["status_loaded"] = True
    res = system.status(ctx={"user_text": "tools page", "intent": "system_status"})
    if res.ok:
        a, b, c = st.columns(3)
        a.metric("CPU", f"{res.data['cpu']:.0f}%")
        b.metric("Memory", f"{res.data['ram']:.0f}%")
        c.metric("Disk", f"{res.data['disk']:.0f}%")
    else:
        ui.error_state("Status is unavailable.", res.message.rstrip("."), "install psutil")

st.subheader("Workspace files")
st.caption(f"Folder: {config.get('default_work_folder')}")
res = files.list_dir(ctx={"user_text": "tools page", "intent": "file_list"})
if res.ok and res.data["items"]:
    st.table([{"Name": i["name"], "Type": "folder" if i["is_dir"] else "file", "Size (bytes)": i["size"]} for i in res.data["items"]])
elif res.ok:
    ui.empty_state("The workspace folder is empty.")
else:
    ui.error_state("The workspace could not be listed.", res.message.rstrip("."), "check allowed folders in Settings")

st.subheader("Applications")
allowed = sorted(apps.allowlist())
if not allowed:
    ui.empty_state("No applications are on the allow-list. Add some in Settings.")
else:
    app = st.selectbox("Application", allowed)
    ctx = {"user_text": "tools page", "intent": "app"}
    left, right = st.columns(2)
    if left.button("Open", type="primary"):
        r = apps.open_app(app, ctx=ctx)
        st.toast(f"Opened {app}." if r.ok else r.message)
    if right.button("Close"):
        r = apps.close_app(app, ctx=ctx)
        if r.error_code == E_NEEDS_CONFIRM:
            st.session_state["close_pending"] = {"app": app, "token": r.data["token"]}
        else:
            st.toast(f"Closed {app}." if r.ok else r.message)
    pend = st.session_state.get("close_pending")
    if pend:
        choice = ui.confirmation_card(f"Close {pend['app']}", pend["app"], key="close_app")
        if choice == "confirm":
            r = apps.close_app(pend["app"], ctx={**ctx, "token": pend["token"]})
            st.toast(f"Closed {pend['app']}." if r.ok else r.message)
            st.session_state.pop("close_pending")
            st.rerun()
        elif choice == "cancel":
            policy.cancel_guarded(pend["token"])
            st.session_state.pop("close_pending")
            st.rerun()

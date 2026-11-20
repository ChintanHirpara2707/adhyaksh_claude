import streamlit as st

from adhyaksh.services import tools as svc
from adhyaksh.ui import components as ui

ui.wide()
ui.page_header("Tools", "System status, workspace files and allowed applications. All actions are checked and logged.")
st.subheader("System status")
if st.button("Refresh status") or "status_loaded" not in st.session_state:
    st.session_state["status_loaded"] = True
    res = svc.system_status(ctx={"user_text": "tools page", "intent": "system_status"})
    if res.ok:
        a, b, c = st.columns(3)
        a.metric("CPU", f"{res.data['cpu']:.0f}%")
        b.metric("Memory", f"{res.data['ram']:.0f}%")
        c.metric("Disk", f"{res.data['disk']:.0f}%")
    else:
        ui.error_state("Status is unavailable.", res.message.rstrip("."), "install psutil")

st.subheader("Workspace files")
st.caption(f"Folder: {svc.get('default_work_folder')}")
res = svc.files_list_dir(ctx={"user_text": "tools page", "intent": "file_list"})
if res.ok and res.data["items"]:
    st.dataframe([{"Name": i["name"], "Type": "folder" if i["is_dir"] else "file",
                   "Size": "" if i["is_dir"] else ui.human_size(i["size"])} for i in res.data["items"]],
                 hide_index=True, width="stretch")
elif res.ok:
    ui.empty_state("The workspace folder is empty.")
else:
    ui.error_state("The workspace could not be listed.", res.message.rstrip("."), "check allowed folders in Settings")

st.subheader("Applications")
allowed = sorted(svc.apps_allowlist())
if not allowed:
    ui.empty_state("No applications are on the allow-list. Add some in Settings.")
else:
    app = st.selectbox("Application", allowed)
    ctx = {"user_text": "tools page", "intent": "app"}
    left, right = st.columns(2)
    if left.button("Open", type="primary"):
        r = svc.apps_open_app(app, ctx=ctx)
        st.toast(f"Opened {app}." if r.ok else r.message)
    if right.button("Close"):
        r = svc.apps_close_app(app, ctx=ctx)
        if r.error_code == svc.E_NEEDS_CONFIRM:
            st.session_state["close_pending"] = {"app": app, "token": r.data["token"]}
        else:
            st.toast(f"Closed {app}." if r.ok else r.message)
    pend = st.session_state.get("close_pending")
    if pend:
        choice = ui.confirmation_card(f"Close {pend['app']}", pend["app"], key="close_app")
        if choice == "confirm":
            r = svc.apps_close_app(pend["app"], ctx={**ctx, "token": pend["token"]})
            st.toast(f"Closed {pend['app']}." if r.ok else r.message)
            st.session_state.pop("close_pending")
            st.rerun()
        elif choice == "cancel":
            svc.policy_cancel_guarded(pend["token"])
            st.session_state.pop("close_pending")
            st.rerun()

st.subheader("Processes")
_sort = st.radio("Sort by", ["memory", "cpu"], horizontal=True, key="proc_sort")
if st.button("Refresh process list") or "procs" not in st.session_state:
    _r = svc.processes_list_processes(10, _sort, ctx={"user_text": "tools page", "intent": "process_list"})
    st.session_state["procs"] = _r.data["processes"] if _r.ok else []
_procs = st.session_state.get("procs") or []
if _procs:
    st.dataframe([{"Program": p["name"], "Memory (MB)": round(p["ram_mb"]), "CPU %": p["cpu_percent"], "Processes": p["count"],
               "System": "yes" if p["protected"] else ""} for p in _procs], hide_index=True, width="stretch")
    _choices = [p["name"] for p in _procs if not p["protected"]]
    if _choices:
        _victim = st.selectbox("Program to end", _choices)
        if st.button("End program"):
            _r = svc.processes_kill_process(_victim, ctx={"user_text": "tools page", "intent": "process_kill"})
            if _r.error_code == svc.E_NEEDS_CONFIRM:
                st.session_state["kill_pending"] = {"name": _victim, "token": _r.data["token"], "shown": _r.data["target"]}
            else:
                st.toast(_r.message or "Done.")
    _kp = st.session_state.get("kill_pending")
    if _kp:
        _choice = ui.confirmation_card(f"End {_kp['shown']}", _kp["name"], key="kill_proc")
        if _choice == "confirm":
            _r = svc.processes_kill_process(_kp["name"], ctx={"user_text": "tools page", "intent": "process_kill"}, token=_kp["token"])
            st.toast(f"Ended {_kp['name']}." if _r.ok else _r.message)
            st.session_state.pop("kill_pending")
            st.session_state.pop("procs", None)
            st.rerun()
        elif _choice == "cancel":
            svc.policy_cancel_guarded(_kp["token"])
            st.session_state.pop("kill_pending")
            st.rerun()

st.subheader("Reminders")
_rem = svc.reminders_list_pending(ctx={"user_text": "tools page", "intent": "reminder_list"})
_items = _rem.data["reminders"] if _rem.ok else []
if not _items:
    ui.empty_state("No pending reminders. Say, for example: remind me to call mom at 6 pm.")
for _it in _items:
    _a, _b = st.columns([5, 1])
    _a.markdown(f"**{_it['text']}** - {_it['when']}")
    if _b.button("Cancel", key=f"rem_{_it['id']}"):
        svc.reminders_cancel(str(_it["id"]), ctx={"user_text": "tools page", "intent": "reminder_cancel"})
        st.rerun()

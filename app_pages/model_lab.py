import json

import streamlit as st

from adhyaksh.services import model_lab as svc
from adhyaksh.ui import components as ui
from adhyaksh.ui import theme

ui.wide()
ui.page_header("Model Lab", "Dataset, training, model comparison and evaluation.")
tab_cmp, tab_data, tab_train = st.tabs(["Comparison", "Dataset", "Training"])

with tab_cmp:
    runs = svc.evaluate_latest_runs()
    if not runs:
        ui.empty_state("No models trained yet. Open the Training tab and start a run.")
    else:
        rows = []
        for r in runs:
            x = json.loads(r["per_language_json"])
            rows.append({"Model": r["name"], "Active": "yes" if r["is_active"] else "no", "Accuracy": round(r["accuracy"], 3),
                         "Macro-F1": round(r["macro_f1"], 3), "Code-mixed F1": round(x["codemixed_macro_f1"], 3),
                         "Size (KB)": round(r["size_bytes"] / 1024), "p50 (ms)": round(r["p50_ms"], 2), "p95 (ms)": round(r["p95_ms"], 2)})
        st.table(rows)
        names = {r["name"]: r for r in runs}
        pick = st.selectbox("Model", list(names))
        run = names[pick]
        if st.button("Use this model for chat", type="primary", disabled=bool(run["is_active"])):
            svc.registry_set_active(run["model_id"])
            svc.set_value("confidence_threshold", str(json.loads(run["per_language_json"])["tau"]))
            st.toast("Active model changed.")
            st.rerun()
        extra = json.loads(run["per_language_json"])
        st.caption("Macro-F1 per language (held-out test split)")
        st.table([{k: round(v, 3) for k, v in extra["per_language"].items()}])
        conf = json.loads(run["confusion_json"])
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.colors import LinearSegmentedColormap
        t = theme.resolve(svc.get("theme"))
        fig, ax = plt.subplots(figsize=(7, 6))
        fig.patch.set_facecolor(t["surface"])
        ax.set_facecolor(t["surface"])
        ax.imshow(conf["matrix"], cmap=LinearSegmentedColormap.from_list("t", [t["surface"], t["accent_strong"]]))
        ax.set_xticks(range(len(conf["labels"])), conf["labels"], rotation=90, color=t["text"], fontsize=7)
        ax.set_yticks(range(len(conf["labels"])), conf["labels"], color=t["text"], fontsize=7)
        ax.set_xlabel("Predicted", color=t["text"])
        ax.set_ylabel("True", color=t["text"])
        ax.set_title("Confusion matrix (test split)", color=t["text"])
        fig.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

with tab_data:
    df = svc.dataset_load()
    st.caption(f"{len(df)} training rows. Dataset hash: {svc.dataset_dataset_hash()}. Generated rows are UNREVIEWED.")
    st.table(df["intent"].value_counts().rename("Rows").reset_index().rename(columns={"intent": "Intent"}))
    st.subheader("Add or correct an example")
    with st.form("add_example", clear_on_submit=True):
        text = st.text_input("Text", max_chars=300)
        intent = st.selectbox("Intent", svc.INTENTS)
        lang = st.selectbox("Language", svc.LANGS)
        source = st.radio("Kind", ["author", "corrected"], horizontal=True)
        if st.form_submit_button("Add example", type="primary"):
            ok, msg = svc.dataset_add_example(text, intent, lang, source)
            (st.toast if ok else st.error)(msg)
    st.caption("Latest rows")
    st.table(df.tail(15))

with tab_train:
    st.markdown("Training runs in the background and never blocks chat. Models use a fixed seed (42).")
    running = svc.train_status()["running"]
    if st.button("Train all models", type="primary", disabled=running):
        if not svc.train_start_background():
            st.toast("A training run is already in progress.")
        st.rerun()

    @st.fragment(run_every=2)
    def progress():
        s = svc.train_status()
        if s["running"]:
            st.markdown("Working: training in progress.")
        for line in s["log"]:
            st.write(line)
        if s["error"]:
            ui.error_state("Training failed.", s["error"], "fix the problem and start again")
        if not s["running"] and s["log"] and not s["error"]:
            st.markdown("Training finished. Open the Comparison tab for the results.")

    progress()

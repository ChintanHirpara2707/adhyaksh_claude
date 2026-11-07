import streamlit as st

from adhyaksh.rag import answerer, loader, retriever
from adhyaksh.ui import components as ui

ui.page_header("Documents", "Index your PDF, DOCX and TXT files and ask questions with cited sources.")
st.caption(f"Retrieval method: {'Gemini embeddings (cloud use enabled)' if retriever.embedding_mode() == 'gemini' else 'TF-IDF (offline)'}")

uploaded = st.file_uploader("Add documents (up to 25 MB each)", type=["pdf", "docx", "txt"], accept_multiple_files=True)
if uploaded and st.button("Index selected files", type="primary"):
    with st.spinner("Working"):
        for f in uploaded:
            res = loader.ingest_bytes(f.name, f.getvalue())
            if res.ok:
                st.toast(f"Indexed {res.data['filename']}: {res.data['chunks']} passages")
            else:
                ui.error_state(f"Could not index {f.name}.", res.message.rstrip("."), "check the file and try again")

docs = loader.list_documents()
if not docs:
    ui.empty_state("No documents indexed. Add a file above to begin.")
else:
    st.table([{"File": d["filename"], "Pages or sections": d["pages"], "Passages": d["chunks"], "Indexed": d["indexed_at"]} for d in docs])
    pick = st.selectbox("Remove a document", [""] + [f"{d['id']}: {d['filename']}" for d in docs])
    if pick and st.button("Remove selected document"):
        loader.delete_document(int(pick.split(":")[0]))
        st.rerun()
    st.subheader("Ask a question")
    q = st.text_input("Question about your documents", max_chars=500)
    if q and st.button("Ask"):
        with st.spinner("Working"):
            res = answerer.answer(q)
        st.markdown(res.data["answer"])
        if res.data["sources"]:
            st.table([{"File": s["file"], "Location": s["location"], "Score": s["score"]} for s in res.data["sources"]])

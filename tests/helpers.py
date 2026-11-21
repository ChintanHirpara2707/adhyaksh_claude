import os
import tempfile
from pathlib import Path

from adhyaksh import db


def fresh_env() -> Path:
    """Point ADHYAKSH at an empty temp data dir and create the schema. The allowed and default work folder is a
    temp folder too, so a test that sends a file command never touches the user's real Documents workspace."""
    d = Path(tempfile.mkdtemp(prefix="adhy_test_"))
    os.environ["ADHYAKSH_DATA_DIR"] = str(d / "data")
    os.environ["ADHYAKSH_MODELS_DIR"] = str(d / "models")
    db.init()
    from adhyaksh import config
    work = d / "workspace"
    work.mkdir()
    ok, msg = config.configure_folders([str(work)], str(work))
    assert ok, msg
    from adhyaksh import logging_setup
    logging_setup.reset()  # the structured log follows the fresh data folder
    from adhyaksh.chat import context
    context._CTX.clear()  # conversation ids restart in a fresh database; drop stale pending state
    from adhyaksh.services import chat as chat_svc
    chat_svc.reset_process_store()  # like a new server process: no current chat, the run starts now
    return d


def open_chat(conversation_id) -> None:
    """Make a conversation the current chat of this 'server run' (what clicking it in the sidebar does)."""
    from adhyaksh.services import chat as chat_svc
    chat_svc.set_current_chat(conversation_id)


def current_chat():
    from adhyaksh.services import chat as chat_svc
    return chat_svc.current_chat()


def make_roots(base: Path) -> tuple[Path, Path]:
    root = base / "workspace"
    root.mkdir(exist_ok=True)
    outside = base / "outside"
    outside.mkdir(exist_ok=True)
    return root.resolve(), outside.resolve()

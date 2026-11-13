import os
import tempfile
from pathlib import Path

from adhyaksh import db


def fresh_env() -> Path:
    """Point ADHYAKSH at an empty temp data dir and create the schema."""
    d = Path(tempfile.mkdtemp(prefix="adhy_test_"))
    os.environ["ADHYAKSH_DATA_DIR"] = str(d / "data")
    os.environ["ADHYAKSH_MODELS_DIR"] = str(d / "models")
    db.init()
    from adhyaksh.chat import context
    context._CTX.clear()  # conversation ids restart in a fresh database; drop stale pending state
    return d


def make_roots(base: Path) -> tuple[Path, Path]:
    root = base / "workspace"
    root.mkdir(exist_ok=True)
    outside = base / "outside"
    outside.mkdir(exist_ok=True)
    return root.resolve(), outside.resolve()

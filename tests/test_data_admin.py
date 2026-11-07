import json
import shutil
import sqlite3
import tempfile
from pathlib import Path

from adhyaksh import config, db
from adhyaksh.nlu import dataset as ds
from adhyaksh.tools import apps
from tests.helpers import fresh_env


def test_export_is_valid_database_and_wipe_clears_everything():
    d = fresh_env()
    db.set_setting("marker", "1")
    (config.uploads_dir() / "u.txt").write_text("x")
    out = d / "exp.db"
    out.write_bytes(db.export_bytes())
    assert sqlite3.connect(out).execute("SELECT value FROM settings WHERE key='marker'").fetchone()[0] == "1"
    db.wipe()
    assert db.get_setting("marker") is None and not list(config.uploads_dir().iterdir())
    assert db.schema_version() == db.MIGRATIONS[-1][0]


def test_configure_folders_validation():
    d = fresh_env()
    ok, _ = config.configure_folders([str(d / "w1"), str(d / "w2")], str(d / "w1" / "sub"))
    assert ok and (d / "w1").is_dir() and len(config.get_allowed_roots()) == 2
    assert not config.configure_folders([str(Path.home())], str(Path.home()))[0]
    assert not config.configure_folders([str(d / "w1")], str(d / "elsewhere"))[0]
    assert not config.configure_folders([], "")[0]


def test_app_allowlist_validation():
    fresh_env()
    assert apps.set_allowlist('{"x": ["cmd"]}').ok
    for bad in ("not json", '["a"]', '{"x": "cmd"}', '{"x": []}', '{"x": [1]}'):
        assert not apps.set_allowlist(bad).ok, bad


def test_add_example_validation_and_hash_change():
    d = Path(tempfile.mkdtemp())
    tr, te = d / "t.csv", d / "c.csv"
    shutil.copy(ds.TRAIN_CSV, tr)
    shutil.copy(ds.TEST_CSV, te)
    before = ds.dataset_hash(tr)
    assert ds.add_example("kindly open paint now", "app_open", "en", path=tr, test_path=te)[0]
    assert ds.dataset_hash(tr) != before and ds.validate(tr, te) == []
    assert not ds.add_example("kindly open paint now", "app_open", "en", path=tr, test_path=te)[0]  # duplicate
    assert not ds.add_example("नमस्ते", "greet", "en", path=tr, test_path=te)[0]  # script mismatch
    assert not ds.add_example("x", "bogus", "en", path=tr, test_path=te)[0]
    assert not ds.add_example("", "greet", "en", path=tr, test_path=te)[0]


def test_voice_component_has_no_hardcoded_colors():
    import re
    html = (Path(__file__).resolve().parent.parent / "adhyaksh" / "voice" / "component" / "index.html").read_text(encoding="utf-8")
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", html)
    assert "streamlit:componentReady" in html and "webkitSpeechRecognition" in html

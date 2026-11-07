import os
import sys
import time

from adhyaksh import config
from adhyaksh.result import E_BLOCKED, E_NEEDS_CONFIRM, E_PATH_DENIED
from adhyaksh.safety import audit, policy
from adhyaksh.tools import apps, files, office, system
from tests.helpers import fresh_env, make_roots

os.environ["ADHYAKSH_NO_OPEN"] = "1"


def _env():
    base = fresh_env()
    root, outside = make_roots(base)
    return root, outside, {"allowed_roots": [root], "base": root}


def _one_row(fn):
    before = audit.count()
    res = fn()
    assert audit.count() == before + 1, "expected exactly one audit row"
    return res


def test_file_lifecycle_with_confirmation():
    root, _, ctx = _env()
    assert _one_row(lambda: files.create("notes.txt", "hello", ctx=ctx)).ok
    assert files.read("notes.txt", ctx=ctx).data["content"] == "hello"
    assert not files.create("notes.txt", "again", ctx=ctx).ok  # never silently overwrites
    assert files.update("notes.txt", "line two", ctx=ctx).ok
    assert files.read("notes.txt", ctx=ctx).data["content"] == "hello\nline two\n"
    over = files.update("notes.txt", "new", mode="overwrite", ctx=ctx)
    assert over.error_code == E_NEEDS_CONFIRM and "hello" in (root / "notes.txt").read_text()
    assert files.update("notes.txt", "new", mode="overwrite", ctx={**ctx, "token": over.data["token"]}).ok
    assert (root / "notes.txt").read_text() == "new"
    d = files.delete("notes.txt", ctx=ctx)
    assert d.error_code == E_NEEDS_CONFIRM and (root / "notes.txt").exists()
    done = _one_row(lambda: files.delete("notes.txt", ctx={**ctx, "token": d.data["token"]}))
    assert done.ok and not (root / "notes.txt").exists()


def test_search_and_list():
    root, _, ctx = _env()
    files.create("sub/alpha_report.txt", "x", ctx=ctx)
    files.create("beta.txt", "y", ctx=ctx)
    m = files.search("report", ctx=ctx).data["matches"]
    assert len(m) == 1 and m[0].endswith("alpha_report.txt")
    assert {i["name"] for i in files.list_dir(ctx=ctx).data["items"]} == {"sub", "beta.txt"}


def test_paths_outside_roots_refused_and_audited():
    root, outside, ctx = _env()
    for call in (lambda: files.read(str(outside / "x.txt"), ctx=ctx),
                 lambda: files.create("../outside/evil.txt", "x", ctx=ctx),
                 lambda: files.delete(str(outside / "x.txt"), ctx=ctx)):
        res = _one_row(call)
        assert res.error_code == E_PATH_DENIED
    assert not (outside / "evil.txt").exists()


def test_invalid_filename_rejected():
    _, _, ctx = _env()
    assert not files.create("bad|name.txt", "x", ctx=ctx).ok


def test_excel_example_reads_back():
    root, _, ctx = _env()
    res = _one_row(lambda: office.names_example(5, ctx=ctx))
    assert res.ok and res.data["rows"] == 5
    from openpyxl import load_workbook
    ws = load_workbook(res.data["path"]).active
    values = [ws.cell(row=i, column=1).value for i in range(1, 7)]
    assert values[:5] == office.INDIAN_NAMES[:5] and values[5] is None
    again = office.names_example(5, ctx=ctx)
    assert again.ok and again.data["path"] != res.data["path"]  # no overwrite


def test_word_document_reads_back():
    _, _, ctx = _env()
    res = office.create_document("memo", ["First paragraph", "Second paragraph"], ctx=ctx)
    from docx import Document
    assert [p.text for p in Document(res.data["path"]).paragraphs] == ["First paragraph", "Second paragraph"]


def test_apps_allowlist_open_refuse_close():
    _, _, _ = _env()
    config.set_value("app_allowlist", '{"sleeper": ["%s", "-c", "import time; time.sleep(30)"]}' % sys.executable.replace("\\", "/"))
    refused = _one_row(lambda: apps.open_app("regedit"))
    assert refused.error_code == E_BLOCKED
    res = _one_row(lambda: apps.open_app("Sleeper"))
    assert res.ok and res.data["pid"]
    c = apps.close_app("sleeper")
    assert c.error_code == E_NEEDS_CONFIRM
    done = apps.close_app("sleeper", ctx={"token": c.data["token"]})
    assert done.ok and done.data["closed"] == 1
    time.sleep(0.2)


def test_system_status():
    _env()
    res = _one_row(system.status)
    assert res.ok and 0 <= res.data["cpu"] <= 100 and 0 < res.data["disk"] <= 100
    t = time.perf_counter()
    system.status()
    assert time.perf_counter() - t < 1.0

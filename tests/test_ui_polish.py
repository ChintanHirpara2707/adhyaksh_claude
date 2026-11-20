"""P7 UI polish: grouped navigation, sidebar status line, readable Activity page, theme handling."""
import ast
from pathlib import Path

from adhyaksh import config
from adhyaksh.result import Result
from adhyaksh.safety import policy
from adhyaksh.services import activity, shell
from adhyaksh.ui import components as ui
from adhyaksh.ui import theme
from tests.helpers import fresh_env

ROOT = Path(__file__).resolve().parent.parent


def test_every_page_is_in_exactly_one_sidebar_section():
    slugs = [s for s, _ in shell.pages()]
    files = sorted(p.stem for p in (ROOT / "app_pages").glob("*.py"))
    assert sorted(slugs) == files and len(slugs) == len(set(slugs))
    assert shell.pages()[0] == ("chat", "Chat") and [n for n, _ in shell.NAV] == ["Assistant", "Tools", "System"]


def test_app_shell_uses_services_not_tools():
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    mods = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module and n.module.startswith("adhyaksh")]
    assert set(mods) <= {"adhyaksh", "adhyaksh.services", "adhyaksh.ui"}, mods


def test_status_line_says_whether_anything_leaves_the_pc(monkeypatch):
    fresh_env()
    lines = shell.status()
    assert "Language model: off (rules and local models)" in lines and "Private mode: nothing leaves this PC" in lines
    config.set_value("llm_provider", "ollama")
    assert "Language model: ollama (on this PC)" in shell.status()
    monkeypatch.setenv("GEMINI_API_KEY", "AIza" + "k" * 30)
    config.set_value("llm_provider", "gemini")
    assert "Language model: off (rules and local models)" in shell.status()  # key but no consent
    config.set_value("cloud_consent", "true")
    lines = shell.status()
    assert "Language model: gemini (cloud)" in lines and "Cloud use: allowed" in lines
    assert not any("AIza" in line for line in lines)


def test_activity_rows_are_readable_filterable_and_exportable():
    fresh_env()
    policy.run_guarded("perf_stats", "system", lambda: Result.success({}))
    policy.deny("app_open", "regedit", "not on the allow-list")
    policy.run_guarded("perf_stats", "temp files", lambda: Result.failure("E_ACTION_FAILED", "no access"))
    rows = activity.rows()
    assert [r["Outcome"] for r in rows] == ["failed", "blocked", "done"]
    assert rows[1]["Action"] == "app open" and rows[1]["Level"] == "L3 blocked" and rows[2]["Level"] == "L0 read-only"
    assert len(rows[0]["Time"]) == 19 and "T" not in rows[0]["Time"]  # local time, no ISO 'T'
    assert activity.summary(rows) == {"done": 1, "failed": 1, "blocked": 1, "cancelled": 0, "rejected": 0}
    assert [r["Target"] for r in activity.filter_rows(rows, ["blocked"])] == ["regedit"]
    assert [r["Target"] for r in activity.filter_rows(rows, None, "TEMP")] == ["temp files"]
    csv = activity.to_csv(rows).decode("utf-8").splitlines()
    assert csv[0].startswith("Time,Action,Target,Level") and len(csv) == 4
    assert activity.outcome("cancelled by user") == "cancelled" and activity.outcome("error: KeyError") == "failed"


def test_human_size():
    assert ui.human_size(512) == "512 B" and ui.human_size(3 * 1024) == "3.0 KB"
    assert ui.human_size(5 * 1024 ** 2) == "5.0 MB" and ui.human_size(3 * 1024 ** 4) == "3072.0 GB" and ui.human_size(None) == ""


def test_pages_do_not_override_the_theme():
    """Only app.py injects the theme; a page injecting 'light' broke the follow-the-OS default in dark mode."""
    for p in (ROOT / "app_pages").glob("*.py"):
        assert "theme.inject" not in p.read_text(encoding="utf-8"), p.name
    css = theme.build_css("")
    assert "prefers-color-scheme: dark" in css and ".adhy-nav-section" in css and ".adhy-status" in css


def test_no_deprecated_width_option():
    for p in list((ROOT / "app_pages").glob("*.py")) + list((ROOT / "adhyaksh" / "ui").glob("*.py")):
        assert "use_container_width" not in p.read_text(encoding="utf-8"), p.name


def test_activity_page_renders_with_filters():
    from streamlit.testing.v1 import AppTest
    fresh_env()
    policy.run_guarded("perf_stats", "system", lambda: Result.success({}))
    policy.deny("app_open", "regedit", "not on the allow-list")
    at = AppTest.from_file(str(ROOT / "app_pages" / "activity.py"), default_timeout=60).run()
    assert not at.exception
    assert [m.value for m in at.metric][:3] == ["1", "0", "1"]
    at.multiselect[0].set_value(["blocked"]).run()
    assert "Showing 1 of 2" in at.caption[0].value

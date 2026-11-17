"""P6 engineering quality: service layer boundary, structured logs, error messages, retries, settings
validation, the Health page and the CI and packaging files. No network is used."""
import ast
import json
import os
from pathlib import Path

import pytest

from adhyaksh import config, errors, logging_setup, net, result
from adhyaksh.result import E_ACTION_FAILED, Result
from adhyaksh.safety import policy
from adhyaksh.services import health
from tests.helpers import fresh_env

ROOT = Path(__file__).resolve().parent.parent
PAGES = sorted((ROOT / "pages").glob("*.py"))
ALLOWED_FOR_PAGES = ("adhyaksh.services", "adhyaksh.ui")


def _adhyaksh_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    mods = []
    for node in ast.walk(tree):  # includes imports inside functions
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "adhyaksh":
            mods.append(node.module if node.module != "adhyaksh" else "adhyaksh:" + ",".join(a.name for a in node.names))
        elif isinstance(node, ast.Import):
            mods += [a.name for a in node.names if a.name.split(".")[0] == "adhyaksh"]
    return mods


# ---- service layer -------------------------------------------------------------------------
def test_pages_import_only_services_and_ui():
    bad = {}
    for p in PAGES:
        wrong = [m for m in _adhyaksh_imports(p) if not m.startswith(ALLOWED_FOR_PAGES)]
        if wrong:
            bad[p.name] = wrong
    assert not bad, f"pages must call adhyaksh only through adhyaksh.services (or adhyaksh.ui): {bad}"


def test_boundary_check_catches_a_direct_tool_import(tmp_path):
    page = tmp_path / "bad_page.py"
    page.write_text("import streamlit as st\nfrom adhyaksh.tools import files\n\ndef f():\n    from adhyaksh import db\n",
                    encoding="utf-8")
    assert [m for m in _adhyaksh_imports(page) if not m.startswith(ALLOWED_FOR_PAGES)] == ["adhyaksh.tools", "adhyaksh:db"]


def test_every_page_has_a_service_an_icon_and_a_route():
    from adhyaksh.ui import icons
    app = (ROOT / "app.py").read_text(encoding="utf-8")
    for p in PAGES:
        assert (ROOT / "adhyaksh" / "services" / p.name).exists(), p.name
        assert p.stem in icons.PAGE_ICONS and f'("{p.stem}",' in app, p.stem


def test_services_expose_what_the_pages_use():
    import importlib
    import re
    for p in PAGES:
        svc = importlib.import_module(f"adhyaksh.services.{p.stem}")
        used = set(re.findall(r"\bsvc\.([A-Za-z_]\w*)", p.read_text(encoding="utf-8")))
        missing = [n for n in used if not hasattr(svc, n)]
        assert not missing, (p.name, missing)


# ---- structured logging ----------------------------------------------------------------------
def test_json_lines_log_with_redaction():
    fresh_env()
    logging_setup.event("unit_test", action="file_read", ok=True, note="key gsk_" + "a1b2c3d4e5f6g7h8i9")
    lines = logging_setup.log_path().read_text(encoding="utf-8").splitlines()
    rec = json.loads(lines[-1])
    assert rec["event"] == "unit_test" and rec["level"] == "INFO" and rec["action"] == "file_read" and rec["ok"] is True
    assert "gsk_" not in lines[-1] and "[REDACTED]" in rec["note"] and rec["ts"].endswith("+00:00")


def test_tool_actions_and_crashes_are_logged():
    fresh_env()
    policy.run_guarded("perf_stats", "system", lambda: Result.success({}))

    def boom():
        raise RuntimeError("disk on fire")
    res = policy.run_guarded("perf_stats", "system", boom)
    assert not res.ok and res.error_code == E_ACTION_FAILED and "RuntimeError" in res.message and "Health page" in res.message
    recs = logging_setup.read_recent(10, "INFO")
    assert recs[0]["event"] == "tool_error" and "disk on fire" in recs[0]["error"]
    assert recs[1]["event"] == "tool_action" and recs[1]["ok"] is True and "ms" in recs[1]
    assert [r["event"] for r in logging_setup.read_recent(10, "WARNING")] == ["tool_error"]


def test_chat_messages_are_logged_without_the_text():
    from adhyaksh.chat import context, engine
    fresh_env()
    engine.handle_message("hello there my secret plan", context.new_conversation())
    raw = logging_setup.log_path().read_text(encoding="utf-8")
    rec = logging_setup.read_recent(1)[0]
    assert rec["event"] == "chat_message" and rec["intent"] and "secret plan" not in raw


def test_logging_never_raises(monkeypatch):
    monkeypatch.setattr(logging_setup, "setup", lambda *a, **k: (_ for _ in ()).throw(OSError("read-only disk")))
    logging_setup.event("x")  # no exception


# ---- error messages ----------------------------------------------------------------------------
def test_every_error_code_has_a_clear_message():
    codes = [v for k, v in vars(result).items() if k.startswith("E_") and isinstance(v, str)]
    assert len(codes) >= 10
    for code in codes:
        assert code in errors.MESSAGES, code
        msg = Result.failure(code).message
        assert msg and msg.endswith(".") and len(msg) > 20, code
    assert Result.failure(E_ACTION_FAILED, "Custom.").message == "Custom."


# ---- retry and timeout -------------------------------------------------------------------------
class _Resp:
    def __init__(self, status):
        self.status_code = status

    def raise_for_status(self):
        import requests
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def test_net_retries_temporary_failures(monkeypatch):
    import requests
    fresh_env()
    calls = []
    answers = [requests.ConnectionError("down"), _Resp(503), _Resp(200)]

    def fake(method, url, **kw):
        calls.append(kw["timeout"])
        a = answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a
    monkeypatch.setattr(requests, "request", fake)
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    assert net.get("https://example.invalid/x", timeout=3).status_code == 200
    assert calls == [3, 3, 3]
    assert [r["event"] for r in logging_setup.read_recent(5, "WARNING")] == ["net_retry", "net_retry"]


def test_net_does_not_retry_a_rejected_request_and_needs_a_timeout(monkeypatch):
    import requests
    calls = []
    monkeypatch.setattr(requests, "request", lambda m, u, **kw: calls.append(1) or _Resp(401))
    with pytest.raises(requests.HTTPError):
        net.post("https://example.invalid/x", timeout=2)
    assert calls == [1]
    with pytest.raises(ValueError):
        net.get("https://example.invalid/x", timeout=0)
    monkeypatch.setattr(requests, "request", lambda m, u, **kw: (_ for _ in ()).throw(requests.Timeout("slow")))
    monkeypatch.setattr(net.time, "sleep", lambda s: None)
    with pytest.raises(requests.Timeout):
        net.get("https://example.invalid/x", timeout=1, attempts=2)


def test_no_module_calls_the_network_without_a_timeout():
    import re
    offenders = []
    for p in (ROOT / "adhyaksh").rglob("*.py"):
        text = p.read_text(encoding="utf-8")
        for m in re.finditer(r"requests\.(get|post|request)\((?:[^()]|\([^()]*\))*\)", text, re.S):
            if "timeout" not in m.group(0):
                offenders.append(f"{p.name}: {m.group(0)[:60]}")
        if "urlopen(" in text and "timeout" not in text:
            offenders.append(p.name)
    assert not offenders, offenders


# ---- settings validation ------------------------------------------------------------------------
def test_settings_are_validated():
    fresh_env()
    with pytest.raises(config.SettingError):
        config.set_value("cloud_consent", "yes")
    with pytest.raises(config.SettingError):
        config.set_value("llm_provider", "openai")
    with pytest.raises(config.SettingError):
        config.set_value("confidence_threshold", "high")
    with pytest.raises(config.SettingError):
        config.set_value("allowed_folders", "C:/Users")  # must be a JSON list
    with pytest.raises(KeyError):
        config.set_value("no_such_setting", "1")
    config.set_value("tts_rate", "9")
    config.set_value("conversation_turns", "0")
    config.set_value("confidence_threshold", "0.55")
    assert config.get("tts_rate") == "1.6" and config.get("conversation_turns") == "1" and config.get("confidence_threshold") == "0.55"
    config.set_value("cloud_consent", True)
    assert config.get_bool("cloud_consent")


def test_bad_stored_values_fall_back_to_defaults_and_show_on_health():
    from adhyaksh import db
    fresh_env()
    db.set_setting("confidence_threshold", "lots")
    db.set_setting("voice_lang", "fr-FR")
    assert config.get("confidence_threshold") == config.DEFAULTS["confidence_threshold"]
    assert config.get_float("confidence_threshold") == 0.6
    assert {p["key"] for p in config.validate_all()} == {"confidence_threshold", "voice_lang"}
    rows = health.service_checks(probe_ollama=False)
    assert any(r["area"] == "Settings" and r["name"] == "voice_lang" and r["state"] == "problem" for r in rows)


def test_rules_cover_only_real_settings():
    assert set(config.RULES) <= set(config.DEFAULTS)
    for key, value in config.DEFAULTS.items():
        config.normalize(key, value)  # every default is valid


# ---- health page ----------------------------------------------------------------------------------
def test_health_lists_every_dependency_and_never_shows_a_key(monkeypatch):
    fresh_env()
    fake_key = "gsk_" + "Z9y8X7w6V5u4T3s2R1q0"
    monkeypatch.setenv("GROQ_API_KEY", fake_key)
    config.set_value("llm_provider", "groq")
    rows = health.checks(probe_ollama=False)
    names = {r["name"] for r in rows}
    for dist, _ in health.CORE:
        assert dist in names
    for dist, _, _ in health.OPTIONAL:
        assert dist in names
    assert {"Python", "Required packages", "Optional packages", "Models", "Storage", "Language model", "Settings"} <= {r["area"] for r in rows}
    assert all(r["state"] in ("ok", "optional", "missing", "problem") for r in rows)
    groq = next(r for r in rows if r["name"] == "Provider: groq")
    assert groq["state"] == "problem" and "not allowed" in groq["detail"]  # key present, no consent
    assert fake_key not in json.dumps(rows)
    assert sum(health.summary(rows).values()) == len(rows)


def test_health_page_renders():
    from streamlit.testing.v1 import AppTest
    fresh_env()
    at = AppTest.from_file(str(ROOT / "pages" / "health.py"), default_timeout=60).run()
    assert not at.exception
    assert any("OK" == m.label for m in at.metric)


# ---- CI and packaging -----------------------------------------------------------------------------
def test_ci_workflow_and_packaging_files():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "windows-latest" in ci and "pytest" in ci and "requirements-core.txt" in ci and "run_eval.py" in ci
    spec = (ROOT / "packaging" / "adhyaksh.spec").read_text(encoding="utf-8")
    assert "launcher.py" in spec and "pages" in spec
    assert (ROOT / "packaging" / "launcher.py").exists()
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for heading in ("## Install", "## Run", "## Tests", "## Health", "## Packaging", "## Privacy"):
        assert heading in readme, heading


def test_env_file_is_never_packaged():
    spec = (ROOT / "packaging" / "adhyaksh.spec").read_text(encoding="utf-8")
    assert ".env\"" not in spec.replace(".env.example", "")
    assert os.path.basename(".env") not in [Path(x).name for x in spec.split("'") if x.endswith(".env")]

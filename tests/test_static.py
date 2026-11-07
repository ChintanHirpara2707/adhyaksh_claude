"""Static checks: no emoji anywhere, no banned calls, no secrets in the repository."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {".git", "venv", ".venv", "__pycache__", ".pytest_cache", "node_modules", "backups", "logs"}
TEXT_EXT = {".py", ".md", ".txt", ".toml", ".html", ".css", ".bat", ".sh", ".csv", ".ini", ".example", ".gitignore"}

EMOJI_RANGES = [
    (0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x2300, 0x23FF),
    (0xFE00, 0xFE0F), (0x200D, 0x200D), (0x20E3, 0x20E3), (0xE0020, 0xE007F),
]


def _files(extra_exclude=()):
    for p in ROOT.rglob("*"):
        if not p.is_file() or any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in TEXT_EXT or p.name in {".gitignore", ".env.example"}:
            if p.name not in extra_exclude:
                yield p


def test_no_emoji_in_source_templates_or_docs():
    bad = []
    for p in _files():
        for ch in p.read_text(encoding="utf-8", errors="ignore"):
            cp = ord(ch)
            if any(lo <= cp <= hi for lo, hi in EMOJI_RANGES):
                bad.append((str(p.relative_to(ROOT)), hex(cp)))
                break
    assert not bad, bad


def _app_sources():
    for p in ROOT.rglob("*.py"):
        rel = p.relative_to(ROOT).parts
        if rel[0] in {"adhyaksh", "pages"} or p.name == "app.py":
            yield p


BANNED = {
    "eval": re.compile(r"(?<![\w.])eval\s*\("),
    "exec": re.compile(r"(?<![\w.])exec\s*\("),
    "shell=True": re.compile(r"shell\s*=\s*True"),
    "os.system": re.compile(r"\bos\.system\s*\("),
}

# adhyaksh/agent/registry.py deliberately uses exec() inside the sandboxed
# run_python tool (Power mode, opt-in, confirmed every time, audited).
BANNED_CALLS_EXCLUDE = {"adhyaksh/agent/registry.py"}


def test_no_banned_calls():
    hits = [(p.name, name) for p in _app_sources()
            if p.relative_to(ROOT).as_posix() not in BANNED_CALLS_EXCLUDE
            for name, rx in BANNED.items()
            if rx.search(p.read_text(encoding="utf-8"))]
    assert not hits, hits


def test_only_db_module_imports_sqlite3():
    offenders = [p.name for p in _app_sources()
                 if p.name != "db.py" and re.search(r"^\s*(import|from)\s+sqlite3", p.read_text(encoding="utf-8"), re.M)]
    assert not offenders, offenders


SECRET_PATTERNS = [re.compile(r"gsk_[A-Za-z0-9]{20,}"), re.compile(r"AIza[0-9A-Za-z_\-]{35}"),
                   re.compile(r"\bsk-[A-Za-z0-9]{32,}")]


def test_no_secrets_in_repository():
    hits = [str(p.relative_to(ROOT)) for p in _files() if p.name != ".env"
            and any(rx.search(p.read_text(encoding="utf-8", errors="ignore")) for rx in SECRET_PATTERNS)]
    assert not hits, hits

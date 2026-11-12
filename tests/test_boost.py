"""Tests for adhyaksh.tools.boost.

Uses pytest tmp_path. No network, no API key, no UI.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from adhyaksh.tools import boost


def _make_file(path: Path, content: bytes = b"x", age_hours: float | None = None) -> Path:
    path.write_bytes(content)
    if age_hours is not None:
        old = time.time() - age_hours * 3600
        os.utime(path, (old, old))
    return path


def test_stats_returns_numbers_in_range():
    s = boost.stats()
    assert 0 <= s["cpu_percent"] <= 100
    assert 0 <= s["ram_percent"] <= 100
    assert s["ram_available_gb"] > 0
    assert 0 <= s["disk_percent"] <= 100
    assert s["disk_free_gb"] > 0


def test_scan_temp_counts_old_files(tmp_path):
    _make_file(tmp_path / "old.txt", age_hours=48)
    _make_file(tmp_path / "new.txt", age_hours=1)
    res = boost.scan_temp(dir=tmp_path, min_age_hours=24)
    assert res["files"] == 1
    assert res["bytes"] > 0


def test_scan_temp_skips_new_files(tmp_path):
    _make_file(tmp_path / "new.txt", age_hours=1)
    res = boost.scan_temp(dir=tmp_path, min_age_hours=24)
    assert res["files"] == 0
    assert res["bytes"] == 0


def test_scan_temp_skips_symlinks(tmp_path):
    if os.name == "nt":
        pytest.skip("symlinks require privileges on Windows")
    real = tmp_path / "real.txt"
    _make_file(real, age_hours=48)
    link = tmp_path / "link.txt"
    os.symlink(real, link)
    res = boost.scan_temp(dir=tmp_path, min_age_hours=24)
    assert res["files"] == 1  # only the real file


def test_clean_temp_deletes_old_file(tmp_path):
    _make_file(tmp_path / "old.txt", age_hours=48)
    res = boost.clean_temp(dir=tmp_path, min_age_hours=24)
    assert res["deleted"] == 1
    assert res["freed_bytes"] > 0
    assert not (tmp_path / "old.txt").exists()


def test_clean_temp_keeps_new_file(tmp_path):
    _make_file(tmp_path / "new.txt", age_hours=1)
    res = boost.clean_temp(dir=tmp_path, min_age_hours=24)
    assert res["deleted"] == 0
    assert res["freed_bytes"] == 0
    assert (tmp_path / "new.txt").exists()


def test_clean_temp_skips_symlink(tmp_path):
    if os.name == "nt":
        pytest.skip("symlinks require privileges on Windows")
    real = tmp_path / "real.txt"
    _make_file(real, age_hours=48)
    link = tmp_path / "link.txt"
    os.symlink(real, link)
    res = boost.clean_temp(dir=tmp_path, min_age_hours=24)
    assert res["deleted"] == 1
    assert real.exists()


def test_clean_temp_does_not_touch_outside(tmp_path):
    inside = tmp_path / "inside.txt"
    _make_file(inside, age_hours=48)
    outside = tmp_path.parent / "outside_should_not_touch.txt"
    _make_file(outside, age_hours=48)
    try:
        res = boost.clean_temp(dir=tmp_path, min_age_hours=24)
        assert res["deleted"] == 1
        assert not inside.exists()
        assert outside.exists()
    finally:
        outside.unlink(missing_ok=True)


def test_clean_temp_removes_empty_subfolders(tmp_path):
    sub = tmp_path / "subdir"
    sub.mkdir()
    _make_file(sub / "old.txt", age_hours=48)
    res = boost.clean_temp(dir=tmp_path, min_age_hours=24)
    assert res["deleted"] == 1
    assert not sub.exists()


def test_scan_temp_default_dir():
    res = boost.scan_temp()
    assert "files" in res
    assert "bytes" in res
    assert isinstance(res["files"], int)
    assert isinstance(res["bytes"], int)

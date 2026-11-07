import os
from pathlib import Path

from adhyaksh.safety import policy
from tests.helpers import fresh_env, make_roots


def _setup():
    base = fresh_env()
    root, outside = make_roots(base)
    return root, outside


def test_levels_by_action():
    root, _ = _setup()
    r = [root]
    f = str(root / "a.txt")
    assert policy.authorize("file_read", f, r).level == 0
    assert policy.authorize("file_create", f, r).level == 1
    d = policy.authorize("file_delete", f, r)
    assert d.level == 2 and d.allowed and d.needs_confirmation
    assert policy.authorize("file_overwrite", f, r).needs_confirmation
    assert policy.authorize("app_close", "notepad").needs_confirmation
    assert not policy.authorize("app_open", "notepad").needs_confirmation


def test_l3_actions_never_allowed():
    d = policy.authorize("shell_exec", "dir")
    assert d.level == 3 and not d.allowed
    d = policy.authorize("made_up_action", "x")
    assert d.level == 3 and not d.allowed


def test_path_outside_roots_denied():
    root, outside = _setup()
    d = policy.authorize("file_read", str(outside / "x.txt"), [root])
    assert not d.allowed and d.level == 3 and "outside" in d.reason


def test_traversal_denied():
    root, outside = _setup()
    sneaky = str(root / ".." / "outside" / "x.txt")
    assert not policy.authorize("file_read", sneaky, [root]).allowed
    assert not policy.authorize("file_read", "../outside/x.txt", [root], base=root).allowed


def test_symlink_escape_denied():
    root, outside = _setup()
    link = root / "link"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except (OSError, NotImplementedError):
        return  # symlinks unavailable on this system
    assert not policy.authorize("file_read", str(link / "x.txt"), [root]).allowed


def test_relative_path_inside_root_allowed():
    root, _ = _setup()
    d = policy.authorize("file_create", "notes.txt", [root], base=root)
    assert d.allowed and d.level == 1


def test_system_paths_denied():
    root, _ = _setup()
    for p in (Path.home(), Path(Path.home().anchor), *policy.system_dirs()):
        assert policy.is_system_path(Path(p).resolve()), p
    assert not policy.authorize("file_read", str(Path.home()), [root]).allowed


def test_system_folder_cannot_be_an_allowed_root():
    d = policy.authorize("file_read", str(Path.home() / "x.txt"), [Path.home()])
    assert not d.allowed


def test_root_itself_cannot_be_deleted():
    root, _ = _setup()
    assert not policy.authorize("file_delete", str(root), [root]).allowed
    assert policy.authorize("file_list", str(root), [root]).allowed


def test_empty_and_null_targets_denied():
    root, _ = _setup()
    assert not policy.authorize("file_read", "", [root]).allowed
    assert not policy.authorize("file_read", "a\x00b", [root]).allowed
    assert not policy.authorize("file_read", str(root / "a"), []).allowed

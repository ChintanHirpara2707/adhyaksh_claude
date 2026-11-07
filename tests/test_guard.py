from adhyaksh.result import (E_CONFIRM_INVALID, E_NEEDS_CONFIRM, E_PATH_DENIED, Result)
from adhyaksh.safety import audit, policy
from adhyaksh.safety.confirm import ConfirmationStore
from tests.helpers import fresh_env, make_roots


class Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return Result.success("done")


def _setup():
    base = fresh_env()
    root, outside = make_roots(base)
    return root, outside, ConfirmationStore()


def test_l0_and_l1_run_and_log_one_row():
    root, _, store = _setup()
    for action in ("file_read", "file_create"):
        run, before = Counter(), audit.count()
        res = policy.run_guarded(action, str(root / "a.txt"), run, allowed_roots=[root], store=store)
        assert res.ok and run.calls == 1 and audit.count() == before + 1


def test_l2_never_runs_without_confirmation():
    root, _, store = _setup()
    run, before = Counter(), audit.count()
    res = policy.run_guarded("file_delete", str(root / "a.txt"), run, allowed_roots=[root], store=store)
    assert res.error_code == E_NEEDS_CONFIRM and run.calls == 0
    assert res.data["token"] and audit.count() == before  # pending is not yet an action


def test_l2_runs_after_confirmation_with_one_row():
    root, _, store = _setup()
    run = Counter()
    target = str(root / "a.txt")
    token = policy.run_guarded("file_delete", target, run, allowed_roots=[root], store=store).data["token"]
    before = audit.count()
    res = policy.run_guarded("file_delete", target, run, token=token, allowed_roots=[root], store=store)
    assert res.ok and run.calls == 1 and audit.count() == before + 1
    assert audit.list_recent(1)[0]["confirmed"] == "confirmed"


def test_token_is_single_use_and_bound_to_target():
    root, _, store = _setup()
    run = Counter()
    a, b = str(root / "a.txt"), str(root / "b.txt")
    token = policy.run_guarded("file_delete", a, run, allowed_roots=[root], store=store).data["token"]
    wrong = policy.run_guarded("file_delete", b, run, token=token, allowed_roots=[root], store=store)
    assert wrong.error_code == E_CONFIRM_INVALID and run.calls == 0
    # the mismatched attempt must not have consumed the real token
    assert policy.run_guarded("file_delete", a, run, token=token, allowed_roots=[root], store=store).ok
    again = policy.run_guarded("file_delete", a, run, token=token, allowed_roots=[root], store=store)
    assert again.error_code == E_CONFIRM_INVALID and run.calls == 1


def test_expired_token_rejected():
    root, _, _ = _setup()
    now = [0.0]
    store = ConfirmationStore(ttl=10, clock=lambda: now[0])
    run, target = Counter(), str(root / "a.txt")
    token = policy.run_guarded("file_delete", target, run, allowed_roots=[root], store=store).data["token"]
    now[0] = 11.0
    res = policy.run_guarded("file_delete", target, run, token=token, allowed_roots=[root], store=store)
    assert res.error_code == E_CONFIRM_INVALID and run.calls == 0


def test_l3_and_denied_paths_never_run():
    root, outside, store = _setup()
    run, before = Counter(), audit.count()
    r1 = policy.run_guarded("shell_exec", "dir", run, store=store)
    r2 = policy.run_guarded("file_read", str(outside / "x"), run, allowed_roots=[root], store=store)
    assert not r1.ok and r2.error_code == E_PATH_DENIED and run.calls == 0
    assert audit.count() == before + 2
    assert audit.list_recent(1)[0]["result"].startswith("blocked")


def test_cancel_writes_one_row_and_blocks_later_confirm():
    root, _, store = _setup()
    run, target = Counter(), str(root / "a.txt")
    token = policy.run_guarded("file_delete", target, run, allowed_roots=[root], store=store).data["token"]
    before = audit.count()
    assert policy.cancel_guarded(token, store=store).ok
    assert audit.count() == before + 1 and audit.list_recent(1)[0]["confirmed"] == "cancelled"
    res = policy.run_guarded("file_delete", target, run, token=token, allowed_roots=[root], store=store)
    assert res.error_code == E_CONFIRM_INVALID and run.calls == 0


def test_runner_exception_is_contained_and_logged():
    root, _, store = _setup()

    def boom():
        raise RuntimeError("x")

    before = audit.count()
    res = policy.run_guarded("file_read", str(root / "a"), boom, allowed_roots=[root], store=store)
    assert not res.ok and audit.count() == before + 1

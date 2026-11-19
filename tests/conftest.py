"""Test isolation, applied to every test automatically.

* Tests never see the real .env: API key variables are removed before anything is imported, and the .env path the
  app reads and writes is pointed at an empty file in a temporary folder (so a test can neither use nor overwrite
  the user's keys).
* Tests never reach the internet: name lookups and connections to anything other than this computer (loopback)
  are refused. A test that forgets to mock a cloud call fails with a clear error instead of calling the provider.
Tests that need a key set a fake one with monkeypatch.setenv; tests that need HTTP mock requests.
"""
from __future__ import annotations

import ipaddress
import os
import socket

import pytest

KEY_VARS = ("GROQ_API_KEY", "GEMINI_API_KEY", "OPENAI_COMPAT_API_KEY")
for _var in KEY_VARS:  # before any test module imports the app
    os.environ.pop(_var, None)


class NetworkDisabled(OSError):
    """Raised when a test tries to reach a host outside this computer."""


def _is_loopback(host) -> bool:
    if host is None:
        return True
    host = str(host).strip("[]").casefold()
    if host in ("localhost", ""):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback
    except ValueError:
        return False


_real_getaddrinfo = socket.getaddrinfo
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _is_loopback(host):
        raise NetworkDisabled(f"network access is disabled in tests (tried to resolve {host})")
    return _real_getaddrinfo(host, *args, **kwargs)


def _target_host(address):
    return address[0] if isinstance(address, tuple) and address else None


def _guarded_connect(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(_target_host(address)):
        raise NetworkDisabled(f"network access is disabled in tests (tried to connect to {address})")
    return _real_connect(self, address)


def _guarded_connect_ex(self, address):
    if self.family in (socket.AF_INET, socket.AF_INET6) and not _is_loopback(_target_host(address)):
        raise NetworkDisabled(f"network access is disabled in tests (tried to connect to {address})")
    return _real_connect_ex(self, address)


socket.getaddrinfo = _guarded_getaddrinfo
socket.socket.connect = _guarded_connect
socket.socket.connect_ex = _guarded_connect_ex


@pytest.fixture(scope="session", autouse=True)
def _no_real_env_file(tmp_path_factory):
    """Point the app's .env path at an empty file for the whole run."""
    from adhyaksh.llm import base as llm
    fake = tmp_path_factory.mktemp("env") / ".env"
    real = llm.ENV_FILE
    llm.ENV_FILE = fake
    yield fake
    llm.ENV_FILE = real


@pytest.fixture(autouse=True)
def _no_keys(monkeypatch):
    """Every test starts without API keys, even if an earlier test stored one."""
    for var in KEY_VARS:
        monkeypatch.delenv(var, raising=False)

"""The test run is sealed off: no real keys, no real .env file, no internet (see tests/conftest.py)."""
import socket

import pytest

from adhyaksh import config
from adhyaksh.llm import base as llm
from tests.conftest import KEY_VARS, NetworkDisabled
from tests.helpers import fresh_env


def test_no_api_key_is_visible():
    import os
    assert not any(os.environ.get(v) for v in KEY_VARS)
    fresh_env()
    assert llm.api_key("gemini") == "" and llm.api_key("groq") == "" and llm.api_key("openai_compat") == ""


def test_the_real_env_file_is_never_used():
    assert llm.ENV_FILE != config.ROOT / ".env"
    llm.set_key("groq", "gsk_fake_for_isolation_test")
    assert llm.ENV_FILE.read_text(encoding="utf-8").strip() == "GROQ_API_KEY=gsk_fake_for_isolation_test"


def test_a_cloud_provider_is_unusable_even_with_consent():
    fresh_env()
    config.set_value("llm_provider", "gemini")
    config.set_value("cloud_consent", "true")
    assert llm.get_provider() is None and not llm.available()


def test_internet_is_refused_but_loopback_works():
    with pytest.raises(NetworkDisabled):
        socket.getaddrinfo("generativelanguage.googleapis.com", 443)
    with pytest.raises(NetworkDisabled):
        socket.create_connection(("8.8.8.8", 53), timeout=1)
    assert socket.getaddrinfo("127.0.0.1", 80)


def test_requests_to_the_cloud_fail_cleanly():
    import requests
    with pytest.raises(requests.ConnectionError):
        requests.get("https://api.groq.com/openai/v1/models", timeout=2)

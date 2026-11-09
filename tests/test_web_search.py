"""Tests for web_search and fetch_page tools (TASK A).

Tests must not need an API key or the network: the HTTP layer is monkeypatched.
"""
from __future__ import annotations

import json

import pytest

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED
from adhyaksh.tools import system


def _set_provider(provider: str) -> None:
    config.set_value("web_search_provider", provider)


class _FakeResponse:
    def __init__(self, text: str, status_code: int = 200) -> None:
        self.text = text
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            from requests import HTTPError

            raise HTTPError(f"{self.status_code} error", response=self)


# ---------------------------------------------------------------------------
# web_search
# ---------------------------------------------------------------------------


def test_web_search_duckduckgo_returns_results(monkeypatch):
    html = (
        '<div class="result"><a class="result__a" href="https://example.com/page">'
        "Example Page</a><div class=\"result__snippet\">A snippet about example.</div></div>"
    )
    monkeypatch.setattr(system, "_http_get", lambda url, timeout=8: html)
    _set_provider("duckduckgo")
    res = system.web_search("test query")
    assert res.ok, res.message
    results = res.data["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Example Page"
    assert results[0]["url"] == "https://example.com/page"
    assert "snippet" in results[0] and "example" in results[0]["snippet"].lower()


def test_web_search_wikipedia_returns_results(monkeypatch):
    payload = {
        "batchcomplete": "",
        "query": {
            "searchinfo": {"totalhits": 1},
            "search": [
                {
                    "title": "Sundar Pichai",
                    "snippet": "<span class=\"searchmatch\">Sundar</span> Pichai is CEO of Google.",
                    "pageid": 25173473,
                }
            ],
        },
    }
    monkeypatch.setattr(system, "_http_get", lambda url, timeout=8: json.dumps(payload))
    _set_provider("wikipedia")
    res = system.web_search("Sundar Pichai")
    assert res.ok, res.message
    results = res.data["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Sundar Pichai"
    assert results[0]["url"] == "https://en.wikipedia.org/wiki/Sundar_Pichai"
    assert "snippet" in results[0]


def test_web_search_empty_results(monkeypatch):
    monkeypatch.setattr(system, "_http_get", lambda url, timeout=8: '<div class="result"></div>')
    _set_provider("duckduckgo")
    res = system.web_search("zzzqwerty nothing")
    assert res.ok
    assert res.data["results"] == []


def test_web_search_provider_falls_back_to_wikipedia(monkeypatch):
    """When the primary provider raises, fall back to Wikipedia."""
    def failing_get(url, *, headers, timeout):
        from requests import RequestException

        raise RequestException("network down")

    monkeypatch.setattr(system, "_http_get", failing_get)
    _set_provider("duckduckgo")
    # duckduckgo raises -> fall back to wikipedia which also raises here -> error
    res = system.web_search("test query")
    assert not res.ok


def test_web_search_invalid_provider(monkeypatch):
    _set_provider("notaprovider")
    res = system.web_search("test query")
    assert not res.ok


# ---------------------------------------------------------------------------
# fetch_page
# ---------------------------------------------------------------------------


def test_fetch_page_returns_clean_text(monkeypatch):
    html = (
        "<html><head><title>Test</title></head>"
        "<body><script>alert('x')</script><p>Hello <b>world</b>!</p>"
        "<style>body{color:red}</style></body></html>"
    )
    monkeypatch.setattr(system, "_http_get", lambda url, timeout=8: html)
    res = system.fetch_page("https://example.com/page")
    assert res.ok, res.message
    text = res.data["text"]
    assert "Hello world" in text
    assert "alert" not in text
    assert "color:red" not in text
    assert "<" not in text and ">" not in text


def test_fetch_page_blocks_localhost(monkeypatch):
    called = []

    def _get(url, *, headers, timeout):
        called.append(url)
        raise SystemExit("should not call")

    monkeypatch.setattr(system, "_http_get", _get)
    for url in ("http://127.0.0.1/", "http://localhost/", "http://[::1]/", "http://localhost.localdomain/"):
        res = system.fetch_page(url)
        assert not res.ok, (url, res.message)
        assert res.error_code == E_ACTION_FAILED
    assert called == [], "must not call _http_get for blocked URLs"


def test_fetch_page_blocks_private_ips(monkeypatch):
    called = []

    def _get(url, *, headers, timeout):
        called.append(url)
        raise SystemExit("should not call")

    monkeypatch.setattr(system, "_http_get", _get)
    for url in ("http://10.0.0.1/", "http://192.168.1.1/", "http://172.16.0.1/"):
        res = system.fetch_page(url)
        assert not res.ok, (url, res.message)
        assert res.error_code == E_ACTION_FAILED
    assert called == []


def test_fetch_page_blocks_non_http_schemes():
    for url in ("ftp://example.com/", "file:///etc/passwd", "javascript:alert(1)"):
        res = system.fetch_page(url)
        assert not res.ok, (url, res.message)
        assert res.error_code == E_ACTION_FAILED


def test_fetch_page_timeout(monkeypatch):
    from requests import Timeout

    def slow_get(url, *, headers, timeout):
        raise Timeout("timed out")

    monkeypatch.setattr(system, "_http_get", slow_get)
    res = system.fetch_page("https://example.com/slow")
    assert not res.ok
    assert "timeout" in (res.error_code + res.message).lower()


def test_fetch_page_http_error(monkeypatch):
    def bad_get(url, *, headers, timeout):
        return _FakeResponse("not found", status_code=404)

    monkeypatch.setattr(system, "_http_get", bad_get)
    res = system.fetch_page("https://example.com/missing")
    assert not res.ok


def test_fetch_page_truncates_long_output(monkeypatch):
    html = "<p>" + ("word " * 50000) + "</p>"
    monkeypatch.setattr(system, "_http_get", lambda url, timeout=8: html)
    res = system.fetch_page("https://example.com/long")
    assert res.ok
    assert len(res.data["text"]) <= 20000 + 20, len(res.data["text"])
    assert res.data["text"].endswith("... (truncated)")

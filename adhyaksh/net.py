"""One place for outgoing HTTP: every request has a timeout and is retried on temporary failures.

Retried: timeouts, connection errors, HTTP 429 and 5xx (two retries, 0.5 s then 1 s pause).
Not retried: other 4xx answers (a wrong key or a bad request will not succeed on a second try).
Callers still decide whether a request may be sent at all (cloud_consent)."""
from __future__ import annotations

import logging
import time

from adhyaksh import logging_setup

DEFAULT_TIMEOUT = 8.0
RETRY_STATUS = {429, 500, 502, 503, 504}
USER_AGENT = "ADHYAKSH-local-assistant/1.0"


def request(method: str, url: str, *, timeout: float = DEFAULT_TIMEOUT, attempts: int = 3,
            pause: float = 0.5, **kwargs):
    """requests.request with a mandatory timeout and retries. Returns the response (raise_for_status already
    called) or raises the last requests exception."""
    import requests

    if not timeout or timeout <= 0:
        raise ValueError("A positive timeout is required for every network call.")
    headers = {"User-Agent": USER_AGENT, **(kwargs.pop("headers", None) or {})}
    host = url.split("/")[2] if "://" in url else url
    last: Exception | None = None
    for i in range(max(1, attempts)):
        try:
            r = requests.request(method, url, timeout=timeout, headers=headers, **kwargs)
            if r.status_code in RETRY_STATUS and i < attempts - 1:
                last = requests.HTTPError(f"HTTP {r.status_code}", response=r)
            else:
                r.raise_for_status()
                return r
        except (requests.Timeout, requests.ConnectionError) as exc:
            last = exc
        logging_setup.event("net_retry", logging.WARNING, host=host, attempt=i + 1, reason=type(last).__name__)
        if i < attempts - 1:
            time.sleep(pause * (2 ** i))
    logging_setup.event("net_failed", logging.ERROR, host=host, attempts=attempts, reason=type(last).__name__)
    assert last is not None
    raise last


def get(url: str, **kwargs):
    return request("GET", url, **kwargs)


def post(url: str, **kwargs):
    return request("POST", url, **kwargs)

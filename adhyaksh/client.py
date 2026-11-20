"""Talk to the background engine (adhyaksh/server.py) when it is running.

The Streamlit console uses this through services/chat.py: with the `background_engine` setting on "auto" and the
engine answering on 127.0.0.1, messages and confirmations go to the engine, so the console, the HUD and voice share
one conversation state; otherwise everything runs in-process exactly as before. The token is read from the data
folder and sent only to 127.0.0.1.
"""
from __future__ import annotations

import time

from adhyaksh import config
from adhyaksh.result import E_NETWORK, Result

_cache = {"at": 0.0, "up": False}
CACHE_SECONDS = 5.0


def _url(path: str) -> str:
    return f"http://127.0.0.1:{int(config.get('server_port'))}{path}"


def _headers() -> dict:
    from adhyaksh import server
    return {server.HEADER: server.token()}


def available() -> bool:
    """True when the setting allows it and the engine answers its health check (checked at most every 5 s)."""
    if config.get("background_engine") != "auto":
        return False
    now = time.monotonic()
    if now - _cache["at"] < CACHE_SECONDS:
        return _cache["up"]
    import requests
    try:
        up = requests.get(_url("/v1/health"), timeout=0.5).status_code == 200
    except requests.RequestException:
        up = False
    _cache.update(at=now, up=up)
    return up


def forget_cache() -> None:
    _cache.update(at=0.0, up=False)


def _call(method: str, path: str, body: dict | None = None, timeout: float = 120.0) -> Result:
    import requests
    try:
        r = requests.request(method, _url(path), json=body, headers=_headers(), timeout=timeout)
    except requests.RequestException as exc:
        forget_cache()
        return Result.failure(E_NETWORK, f"The background engine did not answer ({type(exc).__name__}).")
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code != 200:
        return Result.failure(data.get("code") or E_NETWORK, data.get("error") or f"HTTP {r.status_code}")
    return Result.success(data)


def message(text: str, conversation_id: int, voice: bool = False, mode: str = "cowork") -> Result:
    return _call("POST", "/v1/message", {"text": text, "conversation_id": conversation_id, "voice": voice, "mode": mode})


def confirm(conversation_id: int, accept: bool) -> Result:
    return _call("POST", "/v1/confirm", {"conversation_id": conversation_id, "accept": accept})


def state() -> dict | None:
    """The engine's current state ({"state", "detail", "since"}), or None when it does not answer."""
    res = _call("GET", "/v1/state", timeout=2.0)
    return res.data if res.ok else None


def voice_status() -> dict:
    res = _call("GET", "/v1/voice", timeout=2.0)
    return res.data if res.ok else {"running": False}


def voice_listen() -> Result:
    return _call("POST", "/v1/voice/listen", timeout=5.0)


def voice_quiet() -> Result:
    return _call("POST", "/v1/voice/stop_speaking", timeout=5.0)


def pending(conversation_id: int) -> dict | None:
    res = _call("GET", f"/v1/pending/{int(conversation_id)}", timeout=5.0)
    return res.data.get("pending") if res.ok else None

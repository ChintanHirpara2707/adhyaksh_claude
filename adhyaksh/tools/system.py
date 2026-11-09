"""System status (CPU, RAM, disk), screenshots, web opening and special folders."""
from __future__ import annotations

import ipaddress
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

import requests

from adhyaksh import config
from adhyaksh.result import E_ACTION_FAILED, Result
from adhyaksh.safety import policy

_CACHE: dict = {"at": 0.0, "data": None}
MIN_INTERVAL = 5.0


def status(*, ctx: dict | None = None) -> Result:
    ctx = ctx or {}

    def go() -> Result:
        try:
            import psutil
        except ImportError:
            return Result.failure(E_ACTION_FAILED, "psutil is not installed.")
        if _CACHE["data"] is None or time.monotonic() - _CACHE["at"] >= MIN_INTERVAL:
            usage = shutil.disk_usage(Path.home().anchor or "/")
            _CACHE.update(at=time.monotonic(), data={
                "cpu": psutil.cpu_percent(interval=0.2), "ram": psutil.virtual_memory().percent,
                "disk": usage.used / usage.total * 100})
        return Result.success(dict(_CACHE["data"]))

    return policy.run_guarded("system_status", "system", go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""))


def screenshot(*, ctx: dict | None = None) -> Result:
    """Take a screenshot with PIL and save it in the default work folder."""
    ctx = ctx or {}
    base = Path((ctx or {}).get("base") or config.get("default_work_folder"))

    def go() -> Result:
        try:
            from PIL import ImageGrab
        except ImportError:
            return Result.failure(E_ACTION_FAILED, "Screenshot is not available (Pillow is not installed).")
        try:
            img = ImageGrab.grab()
        except Exception as exc:  # pragma: no cover - environment dependent
            return Result.failure(E_ACTION_FAILED, f"Could not take a screenshot: {exc}.")
        stamp = time.strftime("%Y%m%d_%H%M%S")
        out = base / f"screenshot_{stamp}.png"
        try:
            base.mkdir(parents=True, exist_ok=True)
            img.save(out, format="PNG")
        except (OSError, PermissionError) as exc:
            return Result.failure(E_ACTION_FAILED, f"Could not save the screenshot: {exc}.")
        return Result.success({"path": str(out)})

    return policy.run_guarded("screenshot", "screenshot", go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""))


def web_open(url: str, *, ctx: dict | None = None) -> Result:
    """Open a URL in the default browser. No allow-list is needed for browsers or websites."""
    ctx = ctx or {}
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url

    def go() -> Result:
        if os.environ.get("ADHYAKSH_NO_OPEN"):
            return Result.success({"url": url, "opened": False, "note": "open disabled in tests"})
        try:
            if os.name == "nt":
                os.startfile(url)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", url])
            else:
                subprocess.Popen(["xdg-open", url])
            return Result.success({"url": url, "opened": True})
        except (OSError, AttributeError) as exc:
            return Result.failure(E_ACTION_FAILED, f"Could not open the browser: {exc}.")

    return policy.run_guarded("web_open", url, go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""))


def open_special_folder(name: str, *, ctx: dict | None = None) -> Result:
    """Open a Windows special folder (Recycle Bin, Downloads, Documents, Desktop)."""
    ctx = ctx or {}
    folders = config.default_special_folders()
    aliases = {"file manager": "explorer", "file explorer": "explorer", "explorer": "explorer"}
    key = (name or "").strip().casefold()
    key = aliases.get(key, key)
    target = folders.get(key)
    if target is None:
        return Result.failure(E_ACTION_FAILED, f"Unknown special folder: {name}.")

    def go() -> Result:
        if os.environ.get("ADHYAKSH_NO_OPEN"):
            return Result.success({"folder": name, "target": target, "opened": False,
                                   "note": "open disabled in tests"})
        try:
            os.startfile(target)  # type: ignore[attr-defined]
            return Result.success({"folder": name, "target": target, "opened": True})
        except (OSError, AttributeError) as exc:
            return Result.failure(E_ACTION_FAILED, f"Could not open {name}: {exc}.")

    return policy.run_guarded("special_folder_open", target, go, user_text=ctx.get("user_text", ""),
                              intent=ctx.get("intent", ""))


_HTTP_USER_AGENT = "AdhyakshAssistant/1.0 (https://example.invalid; contact: example@example.invalid)"

_SEARCH_PROVIDERS = {
    "duckduckgo": "https://duckduckgo.com/html/",
    "wikipedia": "https://en.wikipedia.org/w/api.php",
}


def _http_get(url: str, timeout: float = 8.0) -> str:
    """GET a URL with a browser-like User-Agent and return the response text."""
    headers = {"User-Agent": _HTTP_USER_AGENT}
    r = requests.get(url, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.text


def _is_blocked_url(url: str) -> bool:
    """Return True if the URL targets localhost or a private/reserved IP range."""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return True
    if parsed.scheme not in ("http", "https"):
        return True
    host = (parsed.hostname or "").lower()
    if not host:
        return True
    if host in ("localhost", "localhost.localdomain") or host.endswith(".local"):
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast
    except ValueError:
        pass
    # Resolve the hostname and check the resolved addresses too.
    try:
        for info in socket.getaddrinfo(host, None):
            addr = info[4][0]
            try:
                ip = ipaddress.ip_address(addr)
                if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
                    return True
            except ValueError:
                continue
    except (OSError, socket.gaierror):
        # Resolution failure: let the request fail naturally at request time.
        pass
    return False


def _clean_html(html: str, max_chars: int = 20000) -> str:
    """Strip HTML tags and entities, returning plain text."""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<!--.*?-->", " ", text, flags=re.DOTALL)
    text = re.sub(r"</(p|div|li|tr|h[1-6]|section|article|header|footer|nav|aside|main|blockquote|pre)>",
                  "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<(p|div|li|tr|h[1-6]|section|article|header|footer|nav|aside|main|blockquote|pre)[^>]*>",
                  "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&nbsp;", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"&#39;", "'", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = text.strip()
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... (truncated)"
    return text


def _parse_duckduckgo(html: str) -> list[dict]:
    """Parse DuckDuckGo HTML search results into {title, url, snippet} dicts."""
    results: list[dict] = []
    for m in re.finditer(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                         html, flags=re.DOTALL | re.IGNORECASE):
        url = m.group(1)
        title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
        start = m.end()
        snippet_m = re.search(r'<div class="result__snippet"[^>]*>(.*?)</div>',
                              html[start:start + 2000], flags=re.DOTALL | re.IGNORECASE)
        snippet = re.sub(r"<[^>]+>", "", snippet_m.group(1)).strip() if snippet_m else ""
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _parse_wikipedia(payload: str) -> list[dict]:
    """Parse Wikipedia API JSON search results into {title, url, snippet} dicts."""
    data = json.loads(payload)
    results: list[dict] = []
    for item in data.get("query", {}).get("search", []):
        title = item.get("title", "")
        snippet = re.sub(r"<[^>]+>", "", item.get("snippet", "")).strip()
        page_title = title.replace(" ", "_")
        url = f"https://en.wikipedia.org/wiki/{page_title}" if title else ""
        if title and url:
            results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _web_search_wikipedia(query: str) -> Result:
    url = "https://en.wikipedia.org/w/api.php" + "?" + urllib.parse.urlencode({
        "action": "query",
        "list": "search",
        "srsearch": query,
        "format": "json",
    })
    try:
        text = _http_get(url, timeout=8.0)
    except Exception as exc:
        return Result.failure(E_ACTION_FAILED, f"Web search failed: {exc}.")
    try:
        results = _parse_wikipedia(text)
    except Exception as exc:
        return Result.failure(E_ACTION_FAILED, f"Failed to parse search results: {exc}.")
    return Result.success({"results": results, "query": query, "provider": "wikipedia"})


def web_search(query: str, *, ctx: dict | None = None) -> Result:
    """Search the web and return a list of results. L0 read-only."""
    ctx = ctx or {}
    provider = config.get("web_search_provider")
    query = query.strip()
    if not query:
        return Result.failure(E_ACTION_FAILED, "No search query supplied.")

    if provider == "duckduckgo":
        url = "https://duckduckgo.com/html/" + "?" + urllib.parse.urlencode({"q": query})
        try:
            html = _http_get(url, timeout=8.0)
        except Exception as exc:
            # Fall back to Wikipedia when the primary provider fails.
            return _web_search_wikipedia(query)
        results = _parse_duckduckgo(html)
        return Result.success({"results": results, "query": query, "provider": "duckduckgo"})
    if provider == "wikipedia":
        return _web_search_wikipedia(query)
    return Result.failure(E_ACTION_FAILED, f"Unknown web search provider: {provider}.")


def fetch_page(url: str, *, ctx: dict | None = None) -> Result:
    """Fetch a page and return cleaned text. L0 read-only."""
    ctx = ctx or {}
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return Result.failure(E_ACTION_FAILED, f"Invalid URL: {url}.")
    if parsed.scheme not in ("http", "https"):
        return Result.failure(E_ACTION_FAILED, f"Unsupported URL scheme: {parsed.scheme or 'none'}.")
    if _is_blocked_url(url):
        return Result.failure(E_ACTION_FAILED, f"URL is not accessible: {url}.")
    try:
        html = _http_get(url, timeout=8.0)
    except Exception as exc:
        return Result.failure(E_ACTION_FAILED, f"Failed to fetch {url}: {exc}.")
    text = _clean_html(html)
    return Result.success({"text": text, "url": url, "site": parsed.hostname or ""})

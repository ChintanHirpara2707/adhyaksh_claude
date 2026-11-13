"""Free, keyless fallback for factual questions: Wikipedia summaries (only with cloud consent).

The question text is sent to wikipedia.org, so callers must check cloud_consent first."""
from __future__ import annotations

_LANGS = {"en": "en", "hi": "hi", "gu": "gu"}
_UA = {"User-Agent": "ADHYAKSH-local-assistant/1.0"}


def lookup(question: str, lang: str = "en", timeout: float = 6.0) -> str | None:
    """Return a short extract of the best-matching article, or None."""
    import requests

    host = f"https://{_LANGS.get(lang, 'en')}.wikipedia.org"
    try:
        r = requests.get(f"{host}/w/api.php", timeout=timeout, headers=_UA,
                         params={"action": "query", "list": "search", "srsearch": question,
                                 "srlimit": 1, "format": "json"})
        r.raise_for_status()
        hits = r.json().get("query", {}).get("search", [])
        if not hits:
            return None
        title = hits[0]["title"]
        r = requests.get(f"{host}/api/rest_v1/page/summary/{requests.utils.quote(title.replace(' ', '_'))}",
                         timeout=timeout, headers=_UA)
        r.raise_for_status()
        extract = (r.json().get("extract") or "").strip()
        return f"{extract}\n\n(Source: Wikipedia, {title})" if extract else None
    except (requests.RequestException, ValueError, KeyError):
        return None

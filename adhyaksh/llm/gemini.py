from __future__ import annotations

from adhyaksh import config
from adhyaksh.llm.base import Provider, api_key

BASE = "https://generativelanguage.googleapis.com/v1beta/models/"


class GeminiProvider(Provider):
    name = "gemini"

    def _call(self, prompt: str, timeout: float) -> str:
        import requests

        r = requests.post(f"{BASE}{self.model()}:generateContent", timeout=timeout,
                          headers={"x-goog-api-key": api_key("gemini")},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"maxOutputTokens": self.max_tokens}})
        r.raise_for_status()
        return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])


def embed(texts: list[str], timeout: float = 8.0) -> list[list[float]]:
    """Embed texts with the configured Gemini embedding model (UNTESTED ON TARGET)."""
    import requests

    out = []
    for t in texts:
        r = requests.post(f"{BASE}{config.get('embedding_model')}:embedContent", timeout=timeout,
                          headers={"x-goog-api-key": api_key("gemini")},
                          json={"content": {"parts": [{"text": t}]}})
        r.raise_for_status()
        out.append(r.json()["embedding"]["values"])
    return out

from __future__ import annotations

from adhyaksh.llm.base import Provider, api_key

URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(Provider):
    name = "groq"

    def _call(self, prompt: str, timeout: float) -> str:
        import requests

        r = requests.post(URL, timeout=timeout, headers={"Authorization": f"Bearer {api_key('groq')}"},
                          json={"model": self.model(), "max_tokens": self.max_tokens,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

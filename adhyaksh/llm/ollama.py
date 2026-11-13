"""Optional local provider: Ollama (free, runs on this computer, nothing leaves the machine)."""
from __future__ import annotations

from adhyaksh.llm.base import Provider

URL = "http://127.0.0.1:11434/api/generate"


class OllamaProvider(Provider):
    name = "ollama"

    def _call(self, prompt: str, timeout: float) -> str:
        import requests

        r = requests.post(URL, timeout=timeout,
                          json={"model": self.model(), "prompt": prompt, "stream": False,
                                "options": {"num_predict": self.max_tokens}})
        r.raise_for_status()
        return r.json().get("response", "")

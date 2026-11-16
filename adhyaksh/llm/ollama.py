"""Optional local provider: Ollama (free, runs on this computer, nothing leaves the machine)."""
from __future__ import annotations

from adhyaksh.llm.base import Provider

URL = "http://127.0.0.1:11434/api/generate"
CHAT_URL = "http://127.0.0.1:11434/api/chat"


def to_ollama_messages(messages: list[dict]) -> list[dict]:
    out = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            out.append({"role": "assistant", "content": m.get("content") or "",
                        "tool_calls": [{"function": {"name": c["name"], "arguments": c.get("arguments") or {}}} for c in m["tool_calls"]]})
        elif m["role"] == "tool":
            out.append({"role": "tool", "content": m.get("content", ""), "tool_name": m.get("name", "")})
        else:
            out.append({"role": m["role"], "content": m.get("content", "")})
    return out


class OllamaProvider(Provider):
    name = "ollama"

    def _call(self, prompt: str, timeout: float) -> str:
        import requests

        r = requests.post(URL, timeout=timeout,
                          json={"model": self.model(), "prompt": prompt, "stream": False,
                                "options": {"num_predict": self.max_tokens}})
        r.raise_for_status()
        return r.json().get("response", "")

    def _chat(self, messages: list[dict], tools: list[dict], timeout: float) -> dict:
        import requests

        payload = {"model": self.model(), "messages": to_ollama_messages(messages), "stream": False,
                   "options": {"num_predict": self.max_tokens}}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
        r = requests.post(CHAT_URL, timeout=max(timeout, 60.0), json=payload)  # local models can be slow to load
        r.raise_for_status()
        message = r.json().get("message") or {}
        calls = []
        for i, c in enumerate(message.get("tool_calls") or []):
            fn = c.get("function") or {}
            args = fn.get("arguments") or {}
            calls.append({"id": f"call_{i}", "name": fn.get("name", ""), "arguments": args if isinstance(args, dict) else {}})
        return {"text": message.get("content") or "", "tool_calls": calls}

from __future__ import annotations

from adhyaksh.llm.base import MAX_TOKENS, Provider, api_key

import json

URL = "https://api.groq.com/openai/v1/chat/completions"


class GroqProvider(Provider):
    name = "groq"

    def _call(self, prompt: str, timeout: float) -> str:
        import requests

        r = requests.post(URL, timeout=timeout, headers={"Authorization": f"Bearer {api_key('groq')}"},
                          json={"model": self.model(), "max_tokens": MAX_TOKENS,
                                "messages": [{"role": "user", "content": prompt}]})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]

    def complete_with_tools(
        self, messages: list[dict], tools: list[dict], timeout: float = 8.0
    ) -> Result:
        import requests

        r = requests.post(URL, timeout=timeout, headers={"Authorization": f"Bearer {api_key('groq')}"},
                          json={"model": self.model(), "messages": messages, "tools": tools})
        r.raise_for_status()
        data = r.json()
        tool_calls: list[dict] = []
        text = ""
        for choice in data.get("choices", []):
            message = choice.get("message", {})
            text = message.get("content", "") or ""
            for tc in message.get("tool_calls", []):
                fn = tc.get("function", {})
                args = fn.get("arguments", "{}")
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except json.JSONDecodeError:
                        args = {}
                tool_calls.append({"name": fn.get("name", ""), "arguments": args})
        return Result.success({"tool_calls": tool_calls, "text": text})

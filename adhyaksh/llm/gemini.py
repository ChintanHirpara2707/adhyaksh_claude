from __future__ import annotations

import json

from adhyaksh import config
from adhyaksh.llm.base import MAX_TOKENS, Provider, api_key

BASE = "https://generativelanguage.googleapis.com/v1beta/models/"


class GeminiProvider(Provider):
    name = "gemini"

    def _call(self, prompt: str, timeout: float) -> str:
        import requests

        r = requests.post(f"{BASE}{self.model()}:generateContent", timeout=timeout,
                          headers={"x-goog-api-key": api_key("gemini")},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"maxOutputTokens": MAX_TOKENS}})
        r.raise_for_status()
        return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])

    def complete_with_tools(
        self, messages: list[dict], tools: list[dict], timeout: float = 8.0
    ) -> Result:
        import requests

        # Convert messages to Gemini format
        contents = []
        for m in messages:
            role = "model" if m["role"] == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": m["content"]}]})

        # Convert tools to Gemini function declarations
        function_declarations = []
        for tool in tools:
            function_declarations.append({
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "parameters": tool.get("parameters", {}),
            })

        r = requests.post(f"{BASE}{self.model()}:generateContent", timeout=timeout,
                          headers={"x-goog-api-key": api_key("gemini")},
                          json={"contents": contents, "tools": [{"functionDeclarations": function_declarations}],
                                "generationConfig": {"maxOutputTokens": MAX_TOKENS}})
        r.raise_for_status()
        data = r.json()
        tool_calls: list[dict] = []
        text = ""
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                if "functionCall" in part:
                    fc = part["functionCall"]
                    tool_calls.append({"name": fc.get("name", ""), "arguments": fc.get("args", {})})
                elif "text" in part:
                    text = part.get("text", "") or ""
        return Result.success({"tool_calls": tool_calls, "text": text})


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

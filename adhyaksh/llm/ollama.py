from __future__ import annotations

import json

from adhyaksh import config
from adhyaksh.llm.base import MAX_TOKENS, Provider, api_key


class OllamaProvider(Provider):
    name = "ollama"

    def _call(self, prompt: str, timeout: float) -> str:
        import requests

        base_url = config.get("ollama_base_url").rstrip("/")
        model = config.get("ollama_model")
        r = requests.post(f"{base_url}/api/generate", timeout=timeout,
                          json={"model": model, "prompt": prompt, "stream": False})
        r.raise_for_status()
        return r.json().get("response", "")

    def complete_with_tools(
        self, messages: list[dict], tools: list[dict], timeout: float = 8.0
    ) -> Result:
        import requests
        import re

        base_url = config.get("ollama_base_url").rstrip("/")
        model = config.get("ollama_model")

        # Build tool descriptions for the prompt
        tool_descriptions = []
        for tool in tools:
            fn = tool.get("function", {})
            tool_descriptions.append(
                f"- {fn.get('name', '')}: {fn.get('description', '')}"
            )
        tool_text = "\n".join(tool_descriptions)

        # Build conversation text
        conversation = ""
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            conversation += f"{role}: {content}\n"

        prompt = (
            "You are ADHYAKSH, a desktop assistant. Available tools:\n"
            f"{tool_text}\n\n"
            "Rules:\n"
            "1. To call a tool, output exactly one line:\n"
            '   TOOL: {"tool": "<name>", "arguments": {"<arg>": "<value>"}}\n'
            "2. To finish, output exactly one line:\n"
            "   ANSWER: <your final reply to the user>\n\n"
            f"{conversation}\nAssistant:"
        )

        r = requests.post(f"{base_url}/api/generate", timeout=timeout,
                          json={"model": model, "prompt": prompt, "stream": False})
        r.raise_for_status()
        text = r.json().get("response", "")

        # Parse tool calls from text
        tool_calls: list[dict] = []
        for m in re.finditer(r"TOOL:\s*(\{.*?\})", text, re.IGNORECASE | re.DOTALL):
            try:
                obj = json.loads(m.group(1))
                if "tool" in obj:
                    tool_calls.append(obj)
            except json.JSONDecodeError:
                pass
        return Result.success({"tool_calls": tool_calls, "text": text})

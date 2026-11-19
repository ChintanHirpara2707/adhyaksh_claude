"""Any OpenAI-compatible chat endpoint: LM Studio, llama.cpp server, vLLM, LocalAI, OpenRouter and others.

Base URL and model come from Settings (openai_compat_url, openai_compat_model); an optional key comes from
OPENAI_COMPAT_API_KEY in the git-ignored .env file. A loopback URL counts as local (no cloud consent needed);
any other host is treated as a cloud provider and needs cloud_consent like Groq and Gemini.
Whether the model supports native tools is not known in advance: the tool-calling layer tries native calls and
switches to the JSON protocol for good when the server rejects them.
"""
from __future__ import annotations

from adhyaksh import config
from adhyaksh.llm.base import Provider, api_key
from adhyaksh.llm.groq import parse_openai_message, to_openai_messages


def chat_url() -> str:
    return config.get("openai_compat_url").rstrip("/") + "/chat/completions"


def _headers() -> dict:
    key = api_key("openai_compat")
    return {"Authorization": f"Bearer {key}"} if key else {}


class OpenAICompatProvider(Provider):
    name = "openai_compat"

    def _call(self, prompt: str, timeout: float) -> str:
        from adhyaksh import net

        r = net.post(chat_url(), timeout=timeout, attempts=2, headers=_headers(),
                     json={"model": self.model(), "max_tokens": self.max_tokens,
                           "messages": [{"role": "user", "content": prompt}]})
        return r.json()["choices"][0]["message"]["content"]

    def _chat(self, messages: list[dict], tools: list[dict], timeout: float) -> dict:
        from adhyaksh import net

        payload = {"model": self.model(), "max_tokens": self.max_tokens, "messages": to_openai_messages(messages)}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"
        r = net.post(chat_url(), timeout=max(timeout, 60.0), attempts=2, headers=_headers(), json=payload)
        return parse_openai_message(r.json()["choices"][0]["message"])

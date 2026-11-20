from __future__ import annotations

import json

from adhyaksh.llm.base import Provider, api_key

URL = "https://api.groq.com/openai/v1/chat/completions"


def to_openai_messages(messages: list[dict]) -> list[dict]:
    """Neutral messages to the OpenAI-compatible wire format used by Groq."""
    out = []
    for m in messages:
        if m["role"] == "assistant" and m.get("tool_calls"):
            out.append({"role": "assistant", "content": m.get("content") or None,
                        "tool_calls": [{"id": c["id"], "type": "function",
                                        "function": {"name": c["name"], "arguments": json.dumps(c.get("arguments") or {})}}
                                       for c in m["tool_calls"]]})
        elif m["role"] == "tool":
            out.append({"role": "tool", "tool_call_id": m.get("tool_call_id", ""), "content": m.get("content", "")})
        else:
            out.append({"role": m["role"], "content": m.get("content", "")})
    return out


def parse_openai_message(message: dict) -> dict:
    calls = []
    for i, c in enumerate(message.get("tool_calls") or []):
        fn = c.get("function") or {}
        args = fn.get("arguments") or {}
        if isinstance(args, str):
            try:
                args = json.loads(args or "{}")
            except ValueError:
                args = {}
        calls.append({"id": c.get("id") or f"call_{i}", "name": fn.get("name", ""), "arguments": args if isinstance(args, dict) else {}})
    return {"text": message.get("content") or "", "tool_calls": calls}


def stream_openai(url: str, headers: dict, model: str, prompt: str, max_tokens: int, timeout: float):
    """Streamed chat completion in the OpenAI format (Groq and OpenAI-compatible servers): server-sent events whose
    choices[0].delta.content holds the next piece."""
    from adhyaksh import net
    from adhyaksh.llm.base import iter_sse
    r = net.post(url, timeout=timeout, attempts=1, stream=True, headers=headers,
                 json={"model": model, "max_tokens": max_tokens, "stream": True,
                       "messages": [{"role": "user", "content": prompt}]})
    with r:
        for event in iter_sse(r):
            choices = event.get("choices") or [{}]
            piece = (choices[0].get("delta") or {}).get("content")
            if piece:
                yield piece


class GroqProvider(Provider):
    name = "groq"

    def _call(self, prompt: str, timeout: float) -> str:
        from adhyaksh import net

        r = net.post(URL, timeout=timeout, attempts=2, headers={"Authorization": f"Bearer {api_key('groq')}"},
                          json={"model": self.model(), "max_tokens": self.max_tokens,
                                "messages": [{"role": "user", "content": prompt}]})
        return r.json()["choices"][0]["message"]["content"]

    def _stream(self, prompt: str, timeout: float):
        yield from stream_openai(URL, {"Authorization": f"Bearer {api_key('groq')}"}, self.model(), prompt,
                                 self.max_tokens, timeout)

    def _chat(self, messages: list[dict], tools: list[dict], timeout: float) -> dict:
        from adhyaksh import net

        payload = {"model": self.model(), "max_tokens": self.max_tokens, "messages": to_openai_messages(messages)}
        if tools:
            payload["tools"] = [{"type": "function", "function": t} for t in tools]
            payload["tool_choice"] = "auto"
        r = net.post(URL, timeout=timeout, attempts=2, headers={"Authorization": f"Bearer {api_key('groq')}"}, json=payload)
        return parse_openai_message(r.json()["choices"][0]["message"])

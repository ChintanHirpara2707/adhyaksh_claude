from __future__ import annotations

from adhyaksh import config
from adhyaksh.llm.base import Provider, api_key

BASE = "https://generativelanguage.googleapis.com/v1beta/models/"


class GeminiProvider(Provider):
    name = "gemini"

    def _call(self, prompt: str, timeout: float) -> str:
        from adhyaksh import net

        r = net.post(f"{BASE}{self.model()}:generateContent", timeout=timeout, attempts=2,
                          headers={"x-goog-api-key": api_key("gemini")},
                          json={"contents": [{"parts": [{"text": prompt}]}],
                                "generationConfig": {"maxOutputTokens": self.max_tokens}})
        return "".join(p.get("text", "") for p in r.json()["candidates"][0]["content"]["parts"])

    def _stream(self, prompt: str, timeout: float):
        """streamGenerateContent with alt=sse: each event carries the next text parts."""
        from adhyaksh import net
        from adhyaksh.llm.base import iter_sse
        r = net.post(f"{BASE}{self.model()}:streamGenerateContent?alt=sse", timeout=timeout, attempts=1, stream=True,
                     headers={"x-goog-api-key": api_key("gemini")},
                     json={"contents": [{"parts": [{"text": prompt}]}],
                           "generationConfig": {"maxOutputTokens": self.max_tokens}})
        with r:
            for event in iter_sse(r):
                for cand in event.get("candidates") or []:
                    for part in (cand.get("content") or {}).get("parts") or []:
                        if part.get("text"):
                            yield part["text"]

    def _chat(self, messages: list[dict], tools: list[dict], timeout: float) -> dict:
        from adhyaksh import net

        system, contents = to_gemini_contents(messages)
        payload: dict = {"contents": contents, "generationConfig": {"maxOutputTokens": self.max_tokens}}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        if tools:
            payload["tools"] = [{"functionDeclarations": [
                {"name": t["name"], "description": t.get("description", ""), "parameters": to_gemini_schema(t["parameters"])}
                for t in tools]}]
        r = net.post(f"{BASE}{self.model()}:generateContent", timeout=timeout, attempts=2,
                          headers={"x-goog-api-key": api_key("gemini")}, json=payload)
        parts = (r.json()["candidates"][0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if "text" in p)
        calls = [{"id": f"call_{i}", "name": p["functionCall"].get("name", ""), "arguments": p["functionCall"].get("args") or {}}
                 for i, p in enumerate(parts) if "functionCall" in p]
        return {"text": text, "tool_calls": calls}


def to_gemini_schema(schema: dict) -> dict:
    """JSON-schema subset accepted by Gemini function declarations (upper-case type names, no extra keys)."""
    out: dict = {}
    if "type" in schema:
        out["type"] = str(schema["type"]).upper()
    if "description" in schema:
        out["description"] = schema["description"]
    if "enum" in schema:
        out["enum"] = list(schema["enum"])
    if "properties" in schema:
        out["properties"] = {k: to_gemini_schema(v) for k, v in schema["properties"].items()}
    if "items" in schema:
        out["items"] = to_gemini_schema(schema["items"])
    if schema.get("required"):
        out["required"] = list(schema["required"])
    return out


def to_gemini_contents(messages: list[dict]) -> tuple[str, list[dict]]:
    """Neutral messages to (system instruction text, contents list)."""
    system, contents = [], []
    for m in messages:
        if m["role"] == "system":
            system.append(m.get("content", ""))
        elif m["role"] == "assistant":
            parts = [{"text": m["content"]}] if m.get("content") else []
            parts += [{"functionCall": {"name": c["name"], "args": c.get("arguments") or {}}} for c in m.get("tool_calls") or []]
            contents.append({"role": "model", "parts": parts or [{"text": ""}]})
        elif m["role"] == "tool":
            contents.append({"role": "user", "parts": [{"functionResponse": {"name": m.get("name", ""),
                                                                               "response": {"result": m.get("content", "")}}}]})
        else:
            contents.append({"role": "user", "parts": [{"text": m.get("content", "")}]})
    return "\n".join(system), contents


def embed(texts: list[str], timeout: float = 8.0) -> list[list[float]]:
    """Embed texts with the configured Gemini embedding model (UNTESTED ON TARGET)."""
    from adhyaksh import net

    out = []
    for t in texts:
        r = net.post(f"{BASE}{config.get('embedding_model')}:embedContent", timeout=timeout, attempts=2,
                     headers={"x-goog-api-key": api_key("gemini")},
                     json={"content": {"parts": [{"text": t}]}})
        out.append(r.json()["embedding"]["values"])
    return out

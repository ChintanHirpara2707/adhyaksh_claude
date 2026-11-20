"""Optional LLM providers over plain HTTPS. The app works fully without any key.

Streaming (F01) is NOT implemented: replies are returned whole. API keys are read from the
environment or a git-ignored .env file and are never logged or stored in the database.
"""
from __future__ import annotations

import json
import os
import urllib.parse
from abc import ABC, abstractmethod

import logging

from adhyaksh import config, logging_setup, persona
from adhyaksh.llm import cache
from adhyaksh.result import E_BLOCKED, E_NO_API_KEY, E_TIMEOUT, Result

PROVIDERS = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "openai_compat": "OPENAI_COMPAT_API_KEY"}
LOCAL_PROVIDERS = {"ollama"}  # run on this computer, no key, no cloud consent needed
KEY_OPTIONAL = {"openai_compat"}  # a local OpenAI-compatible server (LM Studio, llama.cpp) needs no key
MAX_TOKENS = 400
ANSWER_TOKENS = 1024
ANSWER_TIMEOUT = 25.0
SYSTEM_PROMPT = (
    persona.STYLE + "\n"
    "Answer any question the user asks: facts, explanations, writing, coding, maths, advice, translation. "
    "You cannot browse the web or perform actions on the computer in this reply."
)
ENV_FILE = config.ROOT / ".env"
CUT_OFF_NOTE = "\n\n(The answer was cut off: the connection to the language model broke.)"


def _load_env() -> None:
    try:
        from dotenv import load_dotenv
        load_dotenv(ENV_FILE, override=False)
    except ImportError:
        if ENV_FILE.exists():
            for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
                k, _, v = line.partition("=")
                if k.strip() and v.strip() and k.strip() not in os.environ:
                    os.environ[k.strip()] = v.strip()


def api_key(provider: str) -> str:
    if provider in LOCAL_PROVIDERS or provider not in PROVIDERS:
        return ""
    _load_env()
    return os.environ.get(PROVIDERS[provider], "").strip()


def mask(key: str) -> str:
    return ("*" * 8 + key[-4:]) if len(key) > 4 else ("*" * len(key))


def set_key(provider: str, key: str) -> None:
    """Write the key to the git-ignored .env file (never to the database or logs)."""
    var = PROVIDERS[provider]
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    lines = [ln for ln in lines if not ln.startswith(var + "=")] + [f"{var}={key.strip()}"]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[var] = key.strip()


def search_link(query: str) -> str:
    return "https://www.google.com/search?q=" + urllib.parse.quote(query)


class Provider(ABC):
    name = ""

    @abstractmethod
    def _call(self, prompt: str, timeout: float) -> str: ...

    max_tokens = MAX_TOKENS

    def complete(self, prompt: str, stream: bool = False, timeout: float = 8.0,
                 max_tokens: int = MAX_TOKENS) -> Result:
        """Timeout 8 s by default, one retry, cached per prompt. stream is accepted but not implemented."""
        import requests

        self.max_tokens = max_tokens
        model = self.model()
        hit = cache.get(self.name, model, prompt)
        if hit is not None:
            return Result.success(hit)
        last = ""
        for _ in range(2):
            try:
                text = self._call(prompt, timeout).strip()
                if text:
                    cache.put(text, self.name, model, prompt)
                    return Result.success(text)
                last = "empty response"
            except requests.Timeout:
                last = "timeout"
            except requests.RequestException as exc:
                last = f"request failed ({type(exc).__name__})"
        code = E_TIMEOUT if last == "timeout" else "E_LLM_FAILED"
        logging_setup.event("llm_failed", logging.WARNING, provider=self.name, call="complete", reason=last)
        return Result.failure(code, f"The language model did not respond: {last}.")

    def model(self) -> str:
        return config.get(f"{self.name}_model")

    # ---- streaming ------------------------------------------------------------------------------------------
    def _stream(self, prompt: str, timeout: float):
        """Provider-specific: yield the reply in pieces as the model writes it."""
        raise NotImplementedError

    def stream(self, prompt: str, timeout: float = 25.0, max_tokens: int = MAX_TOKENS):
        """Yield the reply piece by piece. If streaming fails before the first piece, the whole reply is fetched
        with complete() and yielded at once; if it breaks midway, the text so far stays and a short note follows.
        The finished reply is cached like complete()."""
        import requests

        self.max_tokens = max_tokens
        model = self.model()
        hit = cache.get(self.name, model, prompt)
        if hit is not None:
            yield hit
            return
        parts: list[str] = []
        try:
            for piece in self._stream(prompt, timeout):
                if piece:
                    parts.append(piece)
                    yield piece
        except (NotImplementedError, requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
            reason = "timeout" if isinstance(exc, requests.Timeout) else type(exc).__name__
            logging_setup.event("llm_stream_failed", logging.WARNING, provider=self.name, reason=reason,
                                after_pieces=len(parts))
            if not parts:
                res = self.complete(prompt, timeout=timeout, max_tokens=max_tokens)  # fall back to a whole reply
                yield res.data if res.ok else res.message
                return
            yield CUT_OFF_NOTE
            return
        text = "".join(parts).strip()
        if text:
            cache.put(text, self.name, model, prompt)
        else:
            res = self.complete(prompt, timeout=timeout, max_tokens=max_tokens)
            yield res.data if res.ok else res.message

    # ---- native tool calling -------------------------------------------------------------
    def _chat(self, messages: list[dict], tools: list[dict], timeout: float) -> dict:
        """Provider-specific call. Returns {"text": str, "tool_calls": [{"id", "name", "arguments": dict}]}."""
        raise NotImplementedError

    def chat(self, messages: list[dict], tools: list[dict] | None = None, timeout: float = 25.0,
             max_tokens: int = 1024) -> Result:
        """Chat with optional tools. Neutral message format: role system/user/assistant/tool; an assistant
        message may carry tool_calls; a tool message carries tool_call_id, name and content.
        Transient network errors are retried in net.py; an empty reply is asked for once more. A failure carries
        data {"status", "body", "failed_generation"} so the tool-calling layer can repair or switch strategy."""
        import requests

        self.max_tokens = max_tokens
        last, code, info = "", "E_LLM_FAILED", {}
        for attempt in range(2):
            try:
                out = self._chat(messages, tools or [], timeout)
                if out.get("text") or out.get("tool_calls"):
                    return Result.success(out)
                last = "empty response"
                continue
            except requests.Timeout:
                last, code = "timeout", E_TIMEOUT
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", 0)
                info = {"status": status, **_error_details(exc.response)}
                hint = {400: "the request was rejected (the model may not support tools)", 401: "the API key was rejected",
                        403: "access was denied", 404: "the model name was not found",
                        429: "the provider's rate limit was reached; try again shortly"}.get(status, f"HTTP {status}")
                last = hint
            except requests.ConnectionError:
                last = "could not connect (is the service running and the network available?)"
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                last = f"unexpected response ({type(exc).__name__})"
            break
        logging_setup.event("llm_failed", logging.WARNING, provider=self.name, call="chat", reason=last,
                            status=info.get("status"))
        verb = "call failed" if info.get("status") else "did not respond"
        return Result.failure(code, f"The language model {verb}: {last}.", data=info)


def _error_details(response) -> dict:
    """Error body (shortened, secrets redacted) and, when the provider returns it, the model's rejected output."""
    try:
        payload = response.json()
    except Exception:
        payload = None
    err = payload.get("error") if isinstance(payload, dict) else None
    failed = err.get("failed_generation") if isinstance(err, dict) else None
    body = json.dumps(payload)[:600] if payload is not None else (getattr(response, "text", "") or "")[:600]
    return {"body": logging_setup.redact(body), "failed_generation": failed or ""}


def provider_is_local(name: str | None = None) -> bool:
    """Ollama always runs on this PC; an OpenAI-compatible server counts as local only at a loopback address."""
    name = config.get("llm_provider") if name is None else name
    if name in LOCAL_PROVIDERS:
        return True
    if name == "openai_compat":
        host = (urllib.parse.urlparse(config.get("openai_compat_url")).hostname or "").casefold()
        return host in ("127.0.0.1", "localhost", "::1")
    return False


def get_provider() -> Provider | None:
    name = config.get("llm_provider")
    if name == "ollama":
        from adhyaksh.llm.ollama import OllamaProvider
        return OllamaProvider()
    if name == "openai_compat":
        if not config.get("openai_compat_model") or not (provider_is_local(name) or api_key(name)):
            return None
        from adhyaksh.llm.openai_compat import OpenAICompatProvider
        return OpenAICompatProvider()
    if name not in PROVIDERS or not api_key(name):
        return None
    from adhyaksh.llm.gemini import GeminiProvider
    from adhyaksh.llm.groq import GroqProvider
    return {"groq": GroqProvider, "gemini": GeminiProvider}[name]()


def is_local() -> bool:
    return provider_is_local()


def available() -> bool:
    """True when a language model can be used now: a local model, or a keyed cloud provider with consent."""
    if get_provider() is None:
        return False
    return is_local() or config.get_bool("cloud_consent")


def chat(messages: list[dict], tools: list[dict] | None = None, timeout: float = ANSWER_TIMEOUT,
         max_tokens: int = ANSWER_TOKENS) -> Result:
    """Tool-calling chat with the configured provider: a local model, or a cloud one only with consent and a key."""
    if not is_local() and not config.get_bool("cloud_consent"):
        return Result.failure(E_BLOCKED, "Cloud use is not enabled in Settings.")
    provider = get_provider()
    if provider is None:
        return Result.failure(E_NO_API_KEY, "No language model provider and key are configured.")
    return provider.chat(messages, tools, timeout=timeout, max_tokens=max_tokens)


def iter_sse(response):
    """The JSON payloads of a server-sent-events response ("data: {...}" lines), stopping at [DONE]."""
    import json as _json
    for line in response.iter_lines(decode_unicode=True):
        if not line or not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if payload == "[DONE]":
            return
        yield _json.loads(payload)


def stream_ask(prompt: str, timeout: float = ANSWER_TIMEOUT, max_tokens: int = ANSWER_TOKENS) -> Result:
    """Like ask(), but the data is a generator of reply pieces (same consent gate; nothing is sent without it)."""
    if not is_local() and not config.get_bool("cloud_consent"):
        return Result.failure(E_BLOCKED, "Cloud use is not enabled in Settings.")
    provider = get_provider()
    if provider is None:
        return Result.failure(E_NO_API_KEY, "No language model provider and key are configured.")
    return Result.success(provider.stream(prompt, timeout=timeout, max_tokens=max_tokens))


def ask(prompt: str, timeout: float = 8.0, max_tokens: int = MAX_TOKENS) -> Result:
    """Send a prompt to the configured provider: a local model, or a cloud one only with consent and a key."""
    if not is_local() and not config.get_bool("cloud_consent"):
        return Result.failure(E_BLOCKED, "Cloud use is not enabled in Settings.")
    provider = get_provider()
    if provider is None:
        return Result.failure(E_NO_API_KEY, "No language model provider and key are configured.")
    return provider.complete(prompt, timeout=timeout, max_tokens=max_tokens)

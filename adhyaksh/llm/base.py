"""Optional LLM providers over plain HTTPS. The app works fully without any key.

Streaming (F01) is NOT implemented: replies are returned whole. API keys are read from the
environment or a git-ignored .env file and are never logged or stored in the database.
"""
from __future__ import annotations

import os
import urllib.parse
from abc import ABC, abstractmethod

import logging

from adhyaksh import config, logging_setup
from adhyaksh.llm import cache
from adhyaksh.result import E_BLOCKED, E_NO_API_KEY, E_TIMEOUT, Result

PROVIDERS = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY"}
LOCAL_PROVIDERS = {"ollama"}  # run on this computer, no key, no cloud consent needed
MAX_TOKENS = 400
ANSWER_TOKENS = 1024
ANSWER_TIMEOUT = 25.0
SYSTEM_PROMPT = (
    "You are ADHYAKSH, a helpful general-purpose assistant running on the user's laptop. "
    "Answer any question the user asks: facts, explanations, writing, coding, maths, advice, translation. "
    "Reply in the language and script the user used (English, Hindi, Gujarati, Hinglish or Gujlish). "
    "Be accurate and concise, use short paragraphs or lists when they help, and say so when you are unsure "
    "instead of guessing. You cannot browse the web or perform actions on the computer in this reply."
)
ENV_FILE = config.ROOT / ".env"


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
    if provider in LOCAL_PROVIDERS:
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

    # ---- native tool calling -------------------------------------------------------------
    def _chat(self, messages: list[dict], tools: list[dict], timeout: float) -> dict:
        """Provider-specific call. Returns {"text": str, "tool_calls": [{"id", "name", "arguments": dict}]}."""
        raise NotImplementedError

    def chat(self, messages: list[dict], tools: list[dict] | None = None, timeout: float = 25.0,
             max_tokens: int = 1024) -> Result:
        """Chat with optional tools. Neutral message format: role system/user/assistant/tool; an assistant
        message may carry tool_calls; a tool message carries tool_call_id, name and content.
        Two attempts with a short pause; a timeout on every request; clear failure messages."""
        import time

        import requests

        self.max_tokens = max_tokens
        last, code = "", "E_LLM_FAILED"
        for attempt in range(2):
            try:
                out = self._chat(messages, tools or [], timeout)
                if out.get("text") or out.get("tool_calls"):
                    return Result.success(out)
                last = "empty response"
            except requests.Timeout:
                last, code = "timeout", E_TIMEOUT
            except requests.HTTPError as exc:
                status = getattr(exc.response, "status_code", 0)
                last = f"HTTP {status}"
                if status in (400, 401, 403, 404):  # will not succeed on retry
                    hint = {400: "the request was rejected (the model may not support tools)", 401: "the API key was rejected",
                            403: "access was denied", 404: "the model name was not found"}[status]
                    logging_setup.event("llm_failed", logging.WARNING, provider=self.name, call="chat", reason=f"HTTP {status}")
                    return Result.failure("E_LLM_FAILED", f"The language model call failed: {hint}.")
            except requests.ConnectionError:
                last = "could not connect (is the service running and the network available?)"
            except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as exc:
                last = f"unexpected response ({type(exc).__name__})"
            if attempt == 0:
                time.sleep(0.5)
        logging_setup.event("llm_failed", logging.WARNING, provider=self.name, call="chat", reason=last)
        return Result.failure(code, f"The language model did not respond: {last}.")


def get_provider() -> Provider | None:
    name = config.get("llm_provider")
    if name == "ollama":
        from adhyaksh.llm.ollama import OllamaProvider
        return OllamaProvider()
    if name not in PROVIDERS or not api_key(name):
        return None
    from adhyaksh.llm.gemini import GeminiProvider
    from adhyaksh.llm.groq import GroqProvider
    return {"groq": GroqProvider, "gemini": GeminiProvider}[name]()


def is_local() -> bool:
    return config.get("llm_provider") in LOCAL_PROVIDERS


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


def ask(prompt: str, timeout: float = 8.0, max_tokens: int = MAX_TOKENS) -> Result:
    """Send a prompt to the configured provider: a local model, or a cloud one only with consent and a key."""
    if not is_local() and not config.get_bool("cloud_consent"):
        return Result.failure(E_BLOCKED, "Cloud use is not enabled in Settings.")
    provider = get_provider()
    if provider is None:
        return Result.failure(E_NO_API_KEY, "No language model provider and key are configured.")
    return provider.complete(prompt, timeout=timeout, max_tokens=max_tokens)

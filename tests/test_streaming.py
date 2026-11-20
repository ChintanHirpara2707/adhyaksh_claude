"""Phase 4a: streamed replies. Provider wire formats are faked at the HTTP layer (requests.request, used by net.py);
no real model is called. Covered: Groq / OpenAI-compatible SSE, Gemini SSE, Ollama NDJSON, the two fallbacks, the
consent gate, the cache, and the engine: only plain questions stream, the reply is saved and guarded at the end."""
import json

import pytest

from adhyaksh import config
from adhyaksh.chat import context, engine
from adhyaksh.llm import base as llm
from adhyaksh.llm import cache
from adhyaksh.result import Result
from tests.helpers import fresh_env


class _Stream:
    """A streaming HTTP response: lines, then optionally an error mid-way."""

    def __init__(self, lines, fail_after=None, status=200):
        self.lines, self.fail_after, self.status_code = lines, fail_after, status
        self.headers = {"Content-Type": "text/event-stream"}

    def iter_lines(self, decode_unicode=True):
        import requests
        for i, line in enumerate(self.lines):
            if self.fail_after is not None and i == self.fail_after:
                raise requests.ConnectionError("dropped")
            yield line

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": "whole reply"}}], "response": "whole reply",
                "candidates": [{"content": {"parts": [{"text": "whole reply"}]}}]}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _sse(*objs):
    return [f"data: {json.dumps(o)}" for o in objs] + ["data: [DONE]"]


@pytest.fixture
def http(monkeypatch):
    fresh_env()
    cache.clear() if hasattr(cache, "clear") else None
    sent = []

    def install(resp_for):
        import requests

        def fake(method, url, **kw):
            sent.append({"url": url, "json": kw.get("json"), "stream": kw.get("stream")})
            return resp_for(url, kw)
        monkeypatch.setattr(requests, "request", fake)
    return install, sent


def _provider(name, monkeypatch):
    config.set_value("llm_provider", name)
    if name in ("groq", "gemini"):
        monkeypatch.setenv(f"{name.upper()}_API_KEY", "test-key-not-real-0123456789")
        config.set_value("cloud_consent", "true")
    if name == "openai_compat":
        config.set_value("openai_compat_model", "local-model")
    return llm.get_provider()


# ---- wire formats --------------------------------------------------------------------------------------------------
def test_groq_streams_server_sent_events(http, monkeypatch):
    install, sent = http
    install(lambda url, kw: _Stream(_sse({"choices": [{"delta": {"content": "Hel"}}]}, {"choices": [{"delta": {"content": "lo."}}]},
                                         {"choices": [{"delta": {}}]})))
    p = _provider("groq", monkeypatch)
    assert list(p.stream("hi")) == ["Hel", "lo."]
    assert sent[0]["json"]["stream"] is True and sent[0]["stream"] is True


def test_openai_compatible_server_streams_the_same_way(http, monkeypatch):
    install, sent = http
    install(lambda url, kw: _Stream(_sse({"choices": [{"delta": {"content": "Local "}}]}, {"choices": [{"delta": {"content": "answer"}}]})))
    p = _provider("openai_compat", monkeypatch)
    assert "".join(p.stream("hi")) == "Local answer" and sent[0]["url"].endswith("/chat/completions")


def test_gemini_streams_with_alt_sse(http, monkeypatch):
    install, sent = http
    install(lambda url, kw: _Stream(_sse({"candidates": [{"content": {"parts": [{"text": "Namaste "}]}}]},
                                         {"candidates": [{"content": {"parts": [{"text": "Priya."}]}}]})))
    p = _provider("gemini", monkeypatch)
    assert "".join(p.stream("hi")) == "Namaste Priya."
    assert ":streamGenerateContent?alt=sse" in sent[0]["url"] and "test-key" not in sent[0]["url"]


def test_ollama_streams_ndjson(http, monkeypatch):
    install, sent = http
    lines = [json.dumps({"response": "Kem "}), json.dumps({"response": "cho?"}), json.dumps({"response": "", "done": True}),
             json.dumps({"response": "never"})]
    install(lambda url, kw: _Stream(lines))
    p = _provider("ollama", monkeypatch)
    assert list(p.stream("hi")) == ["Kem ", "cho?"] and sent[0]["json"]["stream"] is True


# ---- fallbacks, cache, consent ---------------------------------------------------------------------------------------
def test_no_streaming_falls_back_to_the_whole_reply(http, monkeypatch):
    install, sent = http
    calls = {"n": 0}

    def resp(url, kw):
        calls["n"] += 1
        if kw.get("stream"):
            import requests
            raise requests.HTTPError("streaming not supported")
        return _Stream([])
    install(resp)
    p = _provider("groq", monkeypatch)
    assert list(p.stream("hi")) == ["whole reply"] and calls["n"] == 2


def test_a_stream_that_breaks_midway_keeps_the_text_and_says_so(http, monkeypatch):
    install, _ = http
    install(lambda url, kw: _Stream(_sse({"choices": [{"delta": {"content": "Half an "}}]},
                                         {"choices": [{"delta": {"content": "answer"}}]}), fail_after=1))
    p = _provider("groq", monkeypatch)
    out = list(p.stream("hi"))
    assert out[0] == "Half an " and out[-1] == llm.CUT_OFF_NOTE


def test_a_finished_stream_is_cached(http, monkeypatch):
    install, sent = http
    install(lambda url, kw: _Stream(_sse({"choices": [{"delta": {"content": "cached"}}]})))
    p = _provider("groq", monkeypatch)
    assert "".join(p.stream("same question")) == "cached"
    assert list(p.stream("same question")) == ["cached"] and len(sent) == 1


def test_stream_ask_keeps_the_consent_gate(http, monkeypatch):
    install, sent = http
    install(lambda url, kw: pytest.fail("nothing may be sent"))
    config.set_value("llm_provider", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "test-key-not-real-0123456789")
    res = llm.stream_ask("hi")
    assert not res.ok and res.error_code == "E_BLOCKED" and not sent


# ---- the engine ----------------------------------------------------------------------------------------------------------
@pytest.fixture
def model(monkeypatch):
    fresh_env()
    config.set_value("llm_provider", "ollama")
    pieces = {"value": ["Photosynthesis ", "makes ", "sugar."]}
    monkeypatch.setattr(llm, "stream_ask", lambda prompt, **k: Result.success(iter(pieces["value"])))
    monkeypatch.setattr(llm, "ask", lambda prompt, **k: Result.success("whole answer"))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: Result.success({"text": "agent answer", "tool_calls": []}))
    return pieces


def test_a_plain_question_streams_and_is_saved_at_the_end(model):
    cid = context.new_conversation()
    r = engine.handle_message("explain photosynthesis", cid, stream=True).data
    assert r["reply"] == "" and r["intent"] == "knowledge_question"
    assert [m["role"] for m in context.history(cid)] == ["user"]  # not saved before it is shown
    assert "".join(r["stream"]) == "Photosynthesis makes sugar."
    assert context.history(cid)[-1]["content"] == "Photosynthesis makes sugar."


def test_without_stream_the_reply_is_whole_as_before(model):
    r = engine.handle_message("explain photosynthesis", context.new_conversation()).data
    assert "stream" not in r and r["reply"]


@pytest.mark.parametrize("text", ["open notepad", "what is 12 * 7", "remember that my car is Audi", "create notes.txt"])
def test_commands_and_rules_are_never_streamed(model, text):
    r = engine.handle_message(text, context.new_conversation(), stream=True).data
    assert "stream" not in r and r["reply"]


def test_a_personal_question_is_not_streamed_to_a_plain_model(model, monkeypatch):
    """'what is my car' needs the user's memory: it goes to the agent (which has the memory tool), never to the
    tool-less streamed answer."""
    from adhyaksh.memory import store
    store.save_fact("my car is Audi")
    monkeypatch.setattr(llm, "stream_ask", lambda *a, **k: pytest.fail("must not stream a personal question"))
    r = engine.handle_message("what is my car", context.new_conversation(), stream=True).data
    assert "stream" not in r and r["reply"]


def test_without_a_model_a_general_question_is_answered_whole(model, monkeypatch):
    config.set_value("llm_provider", "")
    r = engine.handle_message("explain photosynthesis", context.new_conversation(), stream=True).data
    assert "stream" not in r and r["reply"]


def test_a_streamed_claim_of_an_action_is_corrected_and_saved_corrected(model):
    model["value"] = ["I have ", "deleted ", "the file."]
    cid = context.new_conversation()
    out = "".join(engine.handle_message("tell me about deleting files", cid, stream=True).data["stream"])
    assert out.startswith("I have deleted the file.") and "have not carried out any action" in out
    assert "have not carried out any action" in context.history(cid)[-1]["content"]


# ---- the chat page ---------------------------------------------------------------------------------------------------------
def test_chat_page_shows_a_streamed_answer(model):
    from pathlib import Path

    from streamlit.testing.v1 import AppTest

    from adhyaksh.chat import identity
    identity.save_name("Tester")
    at = AppTest.from_file(str(Path(__file__).resolve().parent.parent / "app_pages" / "chat.py"), default_timeout=60).run()
    at.chat_input[0].set_value("explain photosynthesis").run()
    assert not at.exception
    texts = [m.value for m in at.markdown]
    assert any("Photosynthesis makes sugar." in t for t in texts)

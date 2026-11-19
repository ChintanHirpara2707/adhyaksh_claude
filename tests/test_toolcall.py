"""Phase 1a: provider-agnostic tool calling. Schema validation and coercion, the JSON protocol, capability
detection and learning, self-repair, salvage of a rejected native call, the OpenAI-compatible provider and the
executor's argument check. No real model or network is used."""
import json

import pytest

from adhyaksh import config
from adhyaksh.agent import registry
from adhyaksh.chat import context, engine
from adhyaksh.llm import base as llm
from adhyaksh.llm import openai_compat, toolcall
from adhyaksh.result import E_BAD_ARGUMENTS, Result
from tests.helpers import fresh_env

TOOLS = [
    {"name": "app_open", "description": "Open an app",
     "parameters": {"type": "object", "properties": {"app": {"type": "string"}}, "required": ["app"]}},
    {"name": "volume_set", "description": "Set volume",
     "parameters": {"type": "object", "properties": {"level": {"type": "integer", "minimum": 0, "maximum": 100},
                                                     "device": {"type": "string", "enum": ["speaker", "mic"]},
                                                     "mute": {"type": "boolean"}},
                    "required": ["level"]}},
]


def _script(monkeypatch, replies, provider="ollama", model="llama3.2:3b"):
    """Scripted llm.chat; records (messages, tool names) per call."""
    fresh_env()
    config.set_value("llm_provider", provider)
    if provider == "ollama":
        config.set_value("ollama_model", model)
    seen = []
    it = iter(replies)

    def fake(messages, tools=None, timeout=25.0, max_tokens=1024):
        seen.append({"messages": [dict(m) for m in messages], "tools": [t["name"] for t in tools or []]})
        out = next(it)
        return out if isinstance(out, Result) else Result.success(out)
    monkeypatch.setattr(llm, "chat", fake)
    return seen


# ---- validation ----------------------------------------------------------------------------------------
@pytest.mark.parametrize("args,clean", [
    ({"level": "40"}, {"level": 40}),
    ({"level": 40.0, "device": "Speaker"}, {"level": 40, "device": "speaker"}),
    ({"level": 5, "mute": "yes"}, {"level": 5, "mute": True}),
    ({"level": 5, "junk": "dropped"}, {"level": 5}),
    ({"level": 5, "device": None}, {"level": 5}),
])
def test_validation_coerces_obvious_slips(args, clean):
    assert toolcall.validate(TOOLS[1]["parameters"], args) == (clean, [])


@pytest.mark.parametrize("args,needle", [
    ({}, "`level` is required"),
    ({"level": "loud"}, "`level` must be integer"),
    ({"level": 140}, "at most 100"),
    ({"level": 10, "device": "headset"}, "must be one of: speaker, mic"),
    ({"level": True}, "must be integer"),
    ("not an object", "must be a JSON object"),
])
def test_validation_reports_precise_problems(args, needle):
    _, problems = toolcall.validate(TOOLS[1]["parameters"], args)
    assert any(needle in p for p in problems), problems


# ---- JSON protocol parsing -------------------------------------------------------------------------------
@pytest.mark.parametrize("text,name,args", [
    ('{"tool_calls": [{"name": "app_open", "arguments": {"app": "notepad"}}]}', "app_open", {"app": "notepad"}),
    ('Sure!\n```json\n{"tool_calls": [{"name": "app_open", "arguments": {"app": "paint"},}]}\n```', "app_open", {"app": "paint"}),
    ('{"name": "app_open", "arguments": "{\\"app\\": \\"chrome\\"}"}', "app_open", {"app": "chrome"}),
    ('{"tool": "app_open", "args": {"app": "edge"}}', "app_open", {"app": "edge"}),
    ('<function=app_open{"app": "calculator"}</function>', "app_open", {"app": "calculator"}),
    ('<function=app_open>{"app": "spotify"}</function>', "app_open", {"app": "spotify"}),
])
def test_parse_reply_accepts_common_shapes(text, name, args):
    out, problem = toolcall.parse_reply(text)
    assert problem == "" and out["tool_calls"][0]["name"] == name and out["tool_calls"][0]["arguments"] == args


def test_parse_reply_answers_and_problems():
    assert toolcall.parse_reply('{"answer": "Paris."}') == ({"text": "Paris.", "tool_calls": []}, "")
    assert toolcall.parse_reply("Paris is the capital.")[0]["text"] == "Paris is the capital."
    assert toolcall.parse_reply('{"tool_calls": [ {"name": ')[1] == "the reply was not valid JSON"
    assert "tool_calls" in toolcall.parse_reply('{"foo": 1}')[1]
    assert toolcall.extract_json('text {"a": "}"} more') == {"a": "}"}  # braces inside strings


# ---- capabilities ---------------------------------------------------------------------------------------
def test_capabilities_table_setting_and_learning():
    fresh_env()
    config.set_value("llm_provider", "ollama")
    assert toolcall.capabilities().strategy == "native"
    config.set_value("ollama_model", "gemma2:2b")
    assert toolcall.capabilities().strategy == "json" and toolcall.capabilities().source == "table"
    config.set_value("ollama_model", "qwen2.5:3b")
    toolcall.learn_json_only("ollama", "qwen2.5:3b")
    assert toolcall.capabilities().strategy == "json" and toolcall.capabilities().source == "learned"
    config.set_value("llm_tool_mode", "native")
    assert toolcall.capabilities().strategy == "native" and toolcall.capabilities().source == "setting"


# ---- turn(): strategies, repair, fallback ---------------------------------------------------------------
def test_native_valid_call_passes_through(monkeypatch):
    seen = _script(monkeypatch, [{"text": "", "tool_calls": [{"id": "a", "name": "volume_set", "arguments": {"level": "30"}}]}])
    out = toolcall.turn([{"role": "user", "content": "volume 30"}], TOOLS).data
    assert out["tool_calls"][0]["arguments"] == {"level": 30} and out["strategy"] == "native" and out["repairs"] == 0
    assert seen[0]["tools"] == ["app_open", "volume_set"]


def test_native_bad_arguments_are_repaired_not_executed(monkeypatch):
    seen = _script(monkeypatch, [
        {"text": "", "tool_calls": [{"id": "a", "name": "volume_set", "arguments": {"level": "loud"}}]},
        {"text": "", "tool_calls": [{"id": "b", "name": "volume_set", "arguments": {"level": 80}}]},
    ])
    out = toolcall.turn([{"role": "user", "content": "make it loud"}], TOOLS).data
    assert out["tool_calls"][0]["arguments"] == {"level": 80} and out["repairs"] == 1
    feedback = seen[1]["messages"][-1]
    assert feedback["role"] == "tool" and "`level` must be integer" in feedback["content"]


def test_repairs_are_bounded(monkeypatch):
    bad = {"text": "", "tool_calls": [{"id": "a", "name": "app_open", "arguments": {}}]}
    seen = _script(monkeypatch, [bad] * 5)
    res = toolcall.turn([{"role": "user", "content": "open"}], TOOLS)
    assert not res.ok and "`app` is required" in res.message and len(seen) == toolcall.MAX_REPAIRS + 1


def test_json_strategy_for_a_model_without_tools(monkeypatch):
    seen = _script(monkeypatch, [{"text": 'Okay: {"tool_calls": [{"name": "app_open", "arguments": {"app": "notepad"}}]}', "tool_calls": []}],
                   model="phi3:mini")
    out = toolcall.turn([{"role": "system", "content": "You are ADHYAKSH."}, {"role": "user", "content": "open notepad"}], TOOLS).data
    assert out["strategy"] == "json" and out["tool_calls"][0]["arguments"] == {"app": "notepad"}
    assert seen[0]["tools"] == []  # no native tools sent
    system = seen[0]["messages"][0]["content"]
    assert system.startswith("You are ADHYAKSH.") and '"name": "volume_set"' in system and "ONE JSON object" in system


def test_json_strategy_repairs_invalid_json_and_converts_history(monkeypatch):
    history = [{"role": "system", "content": "sys"}, {"role": "user", "content": "open notepad then paint"},
               {"role": "assistant", "content": "", "tool_calls": [{"id": "c1", "name": "app_open", "arguments": {"app": "notepad"}}]},
               {"role": "tool", "tool_call_id": "c1", "name": "app_open", "content": '{"status": "ok"}'}]
    seen = _script(monkeypatch, [{"text": "{not json", "tool_calls": []},
                                 {"text": '{"tool_calls": [{"name": "app_open", "arguments": {"app": "paint"}}]}', "tool_calls": []}],
                   model="gemma2:2b")
    out = toolcall.turn(history, TOOLS).data
    assert out["tool_calls"][0]["arguments"] == {"app": "paint"} and out["repairs"] == 1
    plain = seen[0]["messages"]
    assert not any(m.get("tool_calls") or m["role"] == "tool" for m in plain)
    assert json.loads(plain[2]["content"]) == {"tool_calls": [{"name": "app_open", "arguments": {"app": "notepad"}}]}
    assert plain[3]["content"].startswith("Tool result for app_open")
    assert "not valid JSON" in seen[1]["messages"][-1]["content"]


def test_tools_rejection_switches_to_json_and_is_remembered(monkeypatch):
    rejected = Result.failure("E_LLM_FAILED", "rejected", data={"status": 400, "body": '{"error": "model does not support tools"}'})
    seen = _script(monkeypatch, [rejected, {"text": '{"answer": "Hello."}', "tool_calls": []}], model="qwen2.5:0.5b")
    out = toolcall.turn([{"role": "user", "content": "hi"}], TOOLS).data
    assert out == {"text": "Hello.", "tool_calls": [], "strategy": "json", "repairs": 1}
    assert seen[0]["tools"] and seen[1]["tools"] == []
    assert toolcall.capabilities().source == "learned"


def test_groq_failed_generation_is_salvaged(monkeypatch):
    failed = Result.failure("E_LLM_FAILED", "rejected", data={
        "status": 400, "body": "tool_use_failed", "failed_generation": '<function=app_open>{"app": "chrome"}</function>'})
    seen = _script(monkeypatch, [failed])
    out = toolcall.turn([{"role": "user", "content": "open chrome"}], TOOLS).data
    assert out["strategy"] == "salvaged" and out["tool_calls"][0]["arguments"] == {"app": "chrome"} and len(seen) == 1


def test_auth_failure_is_not_retried_or_switched(monkeypatch):
    seen = _script(monkeypatch, [Result.failure("E_LLM_FAILED", "The language model call failed: the API key was rejected.",
                                                data={"status": 401, "body": ""})])
    res = toolcall.turn([{"role": "user", "content": "hi"}], TOOLS)
    assert not res.ok and "key was rejected" in res.message and len(seen) == 1


# ---- provider layer --------------------------------------------------------------------------------------
class _HTTPResp:
    def __init__(self, status, payload):
        self.status_code, self._p, self.text = status, payload, json.dumps(payload)

    def json(self):
        return self._p

    def raise_for_status(self):
        import requests
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)


def test_provider_failure_carries_status_body_and_failed_generation(monkeypatch):
    import requests
    fresh_env()
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "x" * 24)
    body = {"error": {"code": "tool_use_failed", "failed_generation": "<function=app_open{}</function>", "message": "key gsk_" + "y" * 24}}
    monkeypatch.setattr(requests, "request", lambda *a, **k: _HTTPResp(400, body))
    from adhyaksh.llm import groq
    res = groq.GroqProvider().chat([{"role": "user", "content": "x"}], TOOLS)
    assert not res.ok and res.data["status"] == 400 and res.data["failed_generation"].startswith("<function=app_open")
    assert "gsk_" not in res.data["body"] and "REDACTED" in res.data["body"]


def test_rate_limit_is_retried_by_net(monkeypatch):
    import requests
    fresh_env()
    monkeypatch.setenv("GROQ_API_KEY", "gsk_" + "x" * 24)
    answers = [_HTTPResp(429, {}), _HTTPResp(200, {"choices": [{"message": {"content": "hi"}}]})]
    monkeypatch.setattr(requests, "request", lambda *a, **k: answers.pop(0))
    monkeypatch.setattr("adhyaksh.net.time.sleep", lambda s: None)
    from adhyaksh.llm import groq
    assert groq.GroqProvider().chat([{"role": "user", "content": "x"}]).data["text"] == "hi"


def test_openai_compat_local_and_cloud(monkeypatch):
    import requests
    fresh_env()
    config.set_value("llm_provider", "openai_compat")
    assert llm.get_provider() is None  # no model name yet
    config.set_value("openai_compat_model", "qwen2.5-7b-instruct")
    assert llm.is_local() and llm.available() and isinstance(llm.get_provider(), openai_compat.OpenAICompatProvider)
    sent = {}

    def fake(method, url, timeout=None, headers=None, json=None):
        sent.update(url=url, headers=headers, json=json)
        return _HTTPResp(200, {"choices": [{"message": {"content": None, "tool_calls": [
            {"id": "q", "type": "function", "function": {"name": "app_open", "arguments": '{"app": "notepad"}'}}]}}]})
    monkeypatch.setattr(requests, "request", fake)
    out = llm.get_provider().chat([{"role": "user", "content": "open notepad"}], TOOLS).data
    assert out["tool_calls"][0]["arguments"] == {"app": "notepad"}
    assert sent["url"] == "http://127.0.0.1:1234/v1/chat/completions" and "Authorization" not in sent["headers"]
    config.set_value("openai_compat_url", "https://openrouter.example/api/v1")
    assert not llm.is_local() and llm.get_provider() is None  # remote needs a key
    monkeypatch.setenv("OPENAI_COMPAT_API_KEY", "sk-" + "z" * 30)
    assert llm.get_provider() is not None and not llm.available()  # and cloud consent
    config.set_value("cloud_consent", "true")
    assert llm.available()
    with pytest.raises(config.SettingError):
        config.set_value("openai_compat_url", "file:///C:/Windows")


# ---- executor argument check ------------------------------------------------------------------------------
def test_executor_refuses_bad_arguments_with_a_clear_message():
    fresh_env()
    tool = registry.get("app_open")
    res = registry._guarded(tool, {}, registry._make_ctx("open", "agent"), tool.fn)
    assert res.error_code == E_BAD_ARGUMENTS and "`app` is required" in res.message


def test_agent_runs_on_a_json_only_model_end_to_end(monkeypatch):
    """The whole loop with a model that has no native tools: the call is parsed, validated and executed."""
    seen = _script(monkeypatch, [{"text": '{"tool_calls": [{"name": "get_time", "arguments": {}}]}', "tool_calls": []},
                                 {"text": '{"answer": "It is noon."}', "tool_calls": []}], model="gemma2:2b")
    r = engine.handle_message("what time is it", context.new_conversation()).data
    assert r["reply"] == "It is noon." and r["intent"] == "agent"
    assert '"status": "ok"' in seen[1]["messages"][-1]["content"]  # tool result fed back as plain text

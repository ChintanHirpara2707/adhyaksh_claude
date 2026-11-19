"""Provider-agnostic tool calling.

One entry point, :func:`turn`, gives the agent a validated model turn whatever the model can do:

* **native** strategy: the provider's own function-calling interface (Groq, Gemini, Ollama, OpenAI-compatible).
* **json** strategy: the tool schemas go into the prompt and the model must answer with one JSON object,
  ``{"tool_calls": [{"name": ..., "arguments": {...}}]}`` or ``{"answer": "..."}``.

The strategy comes from :func:`capabilities` (a known-model table, the ``llm_tool_mode`` setting, and what was
learned at run time: a model that rejects tools is remembered as JSON-only). Every call is checked against its JSON
schema; a malformed reply, an unknown tool or a bad argument is sent back to the model with a precise error for up
to ``MAX_REPAIRS`` repairs. Calls that still fail validation are never executed.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass

from adhyaksh import config, logging_setup
from adhyaksh.result import Result

MAX_REPAIRS = 2
_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}
# Local models known not to support native tool calls in Ollama (family prefix before the colon).
_NO_NATIVE_PREFIXES = ("gemma", "phi", "tinyllama", "llama2", "mistral:7b-instruct-v0.1", "codellama", "deepseek-r1")


# ---- schema validation -------------------------------------------------------------------------------
def _coerce(value, kind: str):
    """Coerce obvious type slips ("40" -> 40, "true" -> True, 3 -> "3"). Returns (value, ok)."""
    if kind == "integer":
        if isinstance(value, bool):
            return value, False
        if isinstance(value, float) and value.is_integer():
            return int(value), True
        if isinstance(value, str) and re.fullmatch(r"\s*-?\d+\s*", value):
            return int(value), True
    elif kind == "number":
        if isinstance(value, str):
            try:
                return float(value) if "." in value else int(value), True
            except ValueError:
                return value, False
    elif kind == "boolean":
        if isinstance(value, str) and value.strip().lower() in ("true", "false", "yes", "no"):
            return value.strip().lower() in ("true", "yes"), True
    elif kind == "string":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value), True
    elif kind == "array" and isinstance(value, (str, int, float)):
        return [value], True
    return value, False


def _check(value, schema: dict, path: str, errors: list[str]):
    kind = schema.get("type")
    if kind in _TYPES:
        expected = _TYPES[kind]
        bad_bool = kind in ("integer", "number") and isinstance(value, bool)
        if not isinstance(value, expected) or bad_bool:
            value, ok = _coerce(value, kind)
            if not ok:
                errors.append(f"`{path}` must be {kind}, got {type(value).__name__}")
                return value
    if "enum" in schema:
        allowed = list(schema["enum"])
        if value not in allowed:
            match = next((a for a in allowed if isinstance(a, str) and isinstance(value, str)
                          and a.casefold() == value.strip().casefold()), None)
            if match is None:
                errors.append(f"`{path}` must be one of: {', '.join(map(str, allowed))}")
                return value
            value = match
    if kind == "string" and isinstance(value, str):
        value = value.strip()
        if schema.get("minLength", 0) and len(value) < schema["minLength"]:
            errors.append(f"`{path}` must not be empty")
    if kind in ("integer", "number") and isinstance(value, (int, float)):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"`{path}` must be at least {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"`{path}` must be at most {schema['maximum']}")
    if kind == "array" and isinstance(value, list) and isinstance(schema.get("items"), dict):
        value = [_check(v, schema["items"], f"{path}[{i}]", errors) for i, v in enumerate(value)]
    if kind == "object" and isinstance(value, dict) and "properties" in schema:
        value = _check_object(value, schema, path, errors)
    return value


def _check_object(value: dict, schema: dict, path: str, errors: list[str]) -> dict:
    props = schema.get("properties") or {}
    out = {}
    for key, sub in props.items():
        if key in value and value[key] is not None and value[key] != "":
            out[key] = _check(value[key], sub, f"{path}.{key}" if path else key, errors)
    for key in schema.get("required") or []:
        if key not in out:
            errors.append(f"`{path + '.' if path else ''}{key}` is required")
    return out  # unknown keys are dropped: tools only receive what their schema declares


def validate(schema: dict, arguments) -> tuple[dict, list[str]]:
    """(clean arguments, errors). Unknown keys are dropped, obvious type slips are coerced."""
    if not isinstance(arguments, dict):
        return {}, ["arguments must be a JSON object"]
    errors: list[str] = []
    clean = _check_object(arguments, schema or {"type": "object", "properties": {}}, "", errors)
    return clean, errors


# ---- capability profile --------------------------------------------------------------------------------
@dataclass(frozen=True)
class Capabilities:
    provider: str
    model: str
    native_tools: bool
    strategy: str  # "native" or "json"
    source: str  # "setting", "learned" or "table"


def _learned() -> list[str]:
    try:
        return list(json.loads(config.get("llm_json_only_models")))
    except (ValueError, TypeError):
        return []


def _model_key(provider: str, model: str) -> str:
    return f"{provider}:{model}".casefold()


def capabilities(provider: str | None = None, model: str | None = None) -> Capabilities:
    provider = provider if provider is not None else config.get("llm_provider")
    if model is None:
        model = config.get(f"{provider}_model") if f"{provider}_model" in config.DEFAULTS else ""
    mode = config.get("llm_tool_mode")
    if mode in ("native", "json"):
        return Capabilities(provider, model, mode == "native", mode, "setting")
    if _model_key(provider, model) in _learned():
        return Capabilities(provider, model, False, "json", "learned")
    native = not (provider == "ollama" and model.casefold().startswith(_NO_NATIVE_PREFIXES))
    return Capabilities(provider, model, native, "native" if native else "json", "table")


def learn_json_only(provider: str, model: str) -> None:
    """Remember that this model rejects native tools, so later turns go straight to the JSON strategy."""
    key = _model_key(provider, model)
    known = _learned()
    if key not in known:
        config.set_value("llm_json_only_models", json.dumps((known + [key])[-50:]))
        logging_setup.event("llm_capability_learned", provider=provider, model=model, native_tools=False)


# ---- JSON protocol ---------------------------------------------------------------------------------------
def protocol_prompt(tools: list[dict]) -> str:
    lines = [
        "TOOLS. You can act only by calling these tools. Reply with ONE JSON object and nothing else:",
        '- to call tools: {"tool_calls": [{"name": "<tool name>", "arguments": {<arguments>}}]}',
        '- to answer the user: {"answer": "<your reply>"}',
        "Use only the tool names and argument names listed below. Do not wrap the JSON in code fences.",
        "Available tools:",
    ]
    for t in tools:
        lines.append(json.dumps({"name": t["name"], "description": t.get("description", ""),
                                 "parameters": t.get("parameters", {})}, ensure_ascii=False))
    return "\n".join(lines)


def to_plain_messages(messages: list[dict], tools: list[dict]) -> list[dict]:
    """Native-style history (assistant tool_calls, tool results) as plain text for the JSON strategy."""
    out: list[dict] = []
    system_done = False
    for m in messages:
        role = m["role"]
        if role == "system" and not system_done:
            out.append({"role": "system", "content": (m.get("content") or "") + "\n\n" + protocol_prompt(tools)})
            system_done = True
        elif role == "assistant" and m.get("tool_calls"):
            calls = [{"name": c["name"], "arguments": c.get("arguments") or {}} for c in m["tool_calls"]]
            out.append({"role": "assistant", "content": json.dumps({"tool_calls": calls}, ensure_ascii=False)})
        elif role == "tool":
            out.append({"role": "user", "content": f"Tool result for {m.get('name', 'tool')}:\n{m.get('content', '')}"})
        else:
            out.append({"role": role, "content": m.get("content") or ""})
    if not system_done:
        out.insert(0, {"role": "system", "content": protocol_prompt(tools)})
    return out


def _balanced_objects(text: str):
    """Yield each top-level {...} substring, respecting strings and escapes."""
    depth, start, in_str, esc = 0, -1, False, False
    for i, ch in enumerate(text):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0:
                yield text[start:i + 1]


def extract_json(text: str):
    """The first JSON object in a reply: tolerates code fences, prose around it and trailing commas."""
    if not text:
        return None
    t = re.sub(r"```(?:json)?", "", text, flags=re.IGNORECASE)
    for chunk in _balanced_objects(t):
        for candidate in (chunk, re.sub(r",\s*([}\]])", r"\1", chunk)):
            try:
                return json.loads(candidate)
            except ValueError:
                continue
    return None


_FN_TAG = re.compile(r"<function=([\w.-]+)>?\s*(\{.*?\})?\s*</function>", re.DOTALL)


def parse_reply(text: str) -> tuple[dict, str]:
    """A JSON-protocol (or salvaged) reply as {"text", "tool_calls"} plus a problem description ("" when fine)."""
    calls: list[dict] = []
    for m in _FN_TAG.finditer(text or ""):  # Groq / Llama style: <function=name{...}</function>
        args = extract_json(m.group(2) or "{}")
        calls.append({"name": m.group(1), "arguments": args if isinstance(args, dict) else {}})
    if calls:
        return _with_ids({"text": "", "tool_calls": calls}), ""
    obj = extract_json(text)
    if obj is None:
        stripped = (text or "").strip()
        if stripped and "{" not in stripped:
            return {"text": stripped, "tool_calls": []}, ""  # plain prose: accept it as the answer
        return {"text": "", "tool_calls": []}, "the reply was not valid JSON"
    if isinstance(obj, dict) and isinstance(obj.get("answer"), str):
        return {"text": obj["answer"], "tool_calls": []}, ""
    raw = obj.get("tool_calls") if isinstance(obj, dict) else None
    if raw is None and isinstance(obj, dict) and ("name" in obj or "tool" in obj):
        raw = [obj]
    if not isinstance(raw, list) or not raw:
        return {"text": "", "tool_calls": []}, 'the JSON must contain "tool_calls" (a list) or "answer" (a string)'
    for item in raw:
        if not isinstance(item, dict):
            return {"text": "", "tool_calls": []}, "each tool call must be a JSON object"
        name = item.get("name") or item.get("tool") or (item.get("function") or {}).get("name")
        args = item.get("arguments", item.get("args", (item.get("function") or {}).get("arguments", {})))
        if isinstance(args, str):
            args = extract_json(args) or {}
        calls.append({"name": str(name or ""), "arguments": args})
    return _with_ids({"text": "", "tool_calls": calls}), ""


def _with_ids(out: dict) -> dict:
    for i, c in enumerate(out["tool_calls"]):
        c.setdefault("id", f"call_{i}")
    return out


# ---- one validated turn ------------------------------------------------------------------------------------
def check_calls(calls: list[dict], tools: list[dict]) -> tuple[list[dict], list[str]]:
    """Validated calls and a list of problems (unknown tools, bad arguments)."""
    by_name = {t["name"]: t for t in tools}
    good, problems = [], []
    for c in calls:
        tool = by_name.get(c.get("name", ""))
        if tool is None:
            problems.append(f"tool `{c.get('name') or '(no name)'}` is not available; available tools: {', '.join(by_name)}")
            continue
        clean, errors = validate(tool.get("parameters") or {}, c.get("arguments"))
        if errors:
            problems.append(f"{tool['name']}: " + "; ".join(errors))
            continue
        good.append({**c, "arguments": clean})
    return good, problems


def _repair_message(problems: list[str], strategy: str) -> str:
    fix = ("Reply again with ONE corrected JSON object only." if strategy == "json"
           else "Call the tools again with corrected arguments, or answer in text.")
    return "Your last reply could not be used: " + "; ".join(problems) + ". " + fix


def _tools_rejected(res: Result) -> bool:
    info = res.data if isinstance(res.data, dict) else {}
    body = (info.get("body") or "").casefold()
    return info.get("status") == 400 and (not body or "tool" in body or "function" in body)


def turn(messages: list[dict], tools: list[dict], *, timeout: float = 25.0, max_tokens: int = 1024) -> Result:
    """One model turn. Success data: {"text", "tool_calls" (validated), "strategy", "repairs"}.
    Failure: the model could not be reached, or gave no usable reply after the repairs."""
    from adhyaksh.llm import base as llm

    caps = capabilities()
    strategy = caps.strategy if tools else "native"
    work = list(messages)
    problems: list[str] = []
    salvaged = False
    for attempt in range(MAX_REPAIRS + 1):
        if strategy == "json":
            res = llm.chat(to_plain_messages(work, tools), [], timeout=timeout, max_tokens=max_tokens)
        else:
            res = llm.chat(work, tools, timeout=timeout, max_tokens=max_tokens)
        if not res.ok:
            info = res.data if isinstance(res.data, dict) else {}
            if strategy == "native" and tools and info.get("failed_generation") and not salvaged:
                salvaged = True  # the model tried to call a tool but the provider rejected the format: repair it
                out, problem = parse_reply(info["failed_generation"])
                if not problem:
                    good, problems = check_calls(out["tool_calls"], tools)
                    if good and not problems:
                        logging_setup.event("llm_tool_salvaged", provider=caps.provider)
                        return Result.success({"text": "", "tool_calls": good, "strategy": "salvaged", "repairs": attempt})
            if strategy == "native" and tools and _tools_rejected(res):
                learn_json_only(caps.provider, caps.model)
                strategy = "json"
                continue
            return res
        out = res.data or {}
        if strategy == "json" and not out.get("tool_calls"):
            out, problem = parse_reply(out.get("text") or "")
            if problem:
                problems = [problem]
                work = work + [{"role": "assistant", "content": res.data.get("text") or ""},
                               {"role": "user", "content": _repair_message(problems, strategy)}]
                continue
        calls = out.get("tool_calls") or []
        if not calls:
            return Result.success({"text": out.get("text") or "", "tool_calls": [], "strategy": strategy, "repairs": attempt})
        good, problems = check_calls(calls, tools)
        if not problems:
            return Result.success({"text": out.get("text") or "", "tool_calls": good, "strategy": strategy, "repairs": attempt})
        logging_setup.event("llm_tool_invalid", logging.WARNING, provider=caps.provider, strategy=strategy,
                            problems=len(problems), attempt=attempt + 1)
        if strategy == "json":
            work = work + [{"role": "assistant", "content": json.dumps({"tool_calls": calls}, ensure_ascii=False, default=str)},
                           {"role": "user", "content": _repair_message(problems, strategy)}]
        else:
            ids = [c.get("id") or f"call_{i}" for i, c in enumerate(calls)]
            work = work + [{"role": "assistant", "content": out.get("text") or "",
                            "tool_calls": [{**c, "id": i} for c, i in zip(calls, ids)]}]
            work += [{"role": "tool", "tool_call_id": i, "name": c.get("name", ""),
                      "content": json.dumps({"status": "error", "error": _repair_message(problems, strategy)})}
                     for c, i in zip(calls, ids)]
    return Result.failure("E_LLM_FAILED", "The language model did not produce a usable tool call: " + "; ".join(problems) + ".",
                          data={"problems": problems})

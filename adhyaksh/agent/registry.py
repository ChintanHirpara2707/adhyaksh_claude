"""Agent tool registry for ADHYAKSH.

Each registered tool exposes a name, a JSON schema (OpenAI-style function
parameters), a permission level and a callable.  Callables are thin wrappers
around the existing :mod:`adhyaksh.tools` / :mod:`adhyaksh.memory` /
:mod:`adhyaksh.rag` functions.  Every callable self-guards through
``safety.policy.run_guarded`` (L3 refusal, L2 confirmation pause), so the agent
relays the call directly and never invokes a tool on the model's behalf without
authorization.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import io
import threading
import builtins as _builtins_mod
import contextlib
from typing import Callable

from adhyaksh import config
from adhyaksh.memory import store
from adhyaksh.result import E_ACTION_FAILED, E_BAD_ARGUMENTS, E_BLOCKED, E_NEEDS_CONFIRM, Result
from adhyaksh.rag import answerer
from adhyaksh.safety import policy
from adhyaksh.tools import apps, audio, display, files, network, office, power, system, windows

# Actions that touch the filesystem (path validation applies).
PATH_ACTIONS = {
    "file_create", "file_read", "file_search", "file_delete",
    "folder_create", "office_create",
}


@dataclass(frozen=True)
class Tool:
    """A single agent tool."""

    name: str
    description: str
    parameters: dict  # JSON schema (OpenAI-style "parameters" object)
    level: int  # permission level (0 read-only, 1 reversible, 2 confirmation, 3 blocked)
    fn: Callable[[dict, dict], Result]  # (arguments, ctx) -> Result


_REGISTRY: dict[str, Tool] = {}


def register(name: str, description: str, parameters: dict, level: int,
             fn: Callable[[dict, dict], Result]) -> Tool:
    """Register a tool and return it."""
    tool = Tool(name, description, parameters, level, fn)
    _REGISTRY[name] = tool
    return tool


def get(name: str) -> Tool | None:
    """Return a registered tool by name, or None."""
    return _REGISTRY.get(name)


def list_tools() -> list[Tool]:
    """Return all registered tools."""
    return list(_REGISTRY.values())


def object_schema(p: dict) -> dict:
    """Bare property maps become object schemas (every listed property required)."""
    if p.get("type") == "object":
        return p
    return {"type": "object", "properties": p, "required": list(p)}


def schemas() -> list[dict]:
    """OpenAI-style function schemas describing every registered tool.

    ``run_python`` is omitted unless Power mode is enabled in Settings.
    """
    include_power = config.get_bool("power_mode")

    return [
        {"name": t.name, "description": t.description, "parameters": object_schema(t.parameters)}
        for t in _REGISTRY.values()
        if not (t.name == "run_python" and not include_power)
    ]


# ---------------------------------------------------------------------------
# Safety-guarded runner
# ---------------------------------------------------------------------------

# Stored (tool, arguments, ctx) keyed by confirmation token so resume() can
# re-execute an L2 call after the user confirms. Kept in memory (one operator).
_RESUME_CALLS: dict[str, tuple[Tool, dict, dict]] = {}


def pop_resume_call(token: str) -> tuple[Tool, dict, dict] | None:
    """Pop and return the stored (tool, arguments, ctx) for a confirmation token."""
    return _RESUME_CALLS.pop(token, None)


def _guarded(tool: Tool, arguments: dict, ctx: dict,
             runner: Callable[[dict, dict], Result]) -> Result:
    """Run one tool call.  Every tool callable self-guards through
    ``safety.policy.run_guarded`` (L3 refusal, L2 confirmation pause), so the
    agent relays the call directly.  L2 results carry the confirmation token in
    ``res.data["token"]``; we remember the call so :func:`resume` can re-run it
    after the user confirms.  Tool failures never raise.
    """
    from adhyaksh.llm import toolcall

    arguments, problems = toolcall.validate(object_schema(tool.parameters), arguments or {})
    if problems:  # never run a tool with missing or malformed arguments; tell the caller exactly what is wrong
        return Result.failure(E_BAD_ARGUMENTS, f"{tool.name}: " + "; ".join(problems) + ".", data={"problems": problems})
    try:
        res = runner(arguments, ctx)
    except Exception as exc:  # tool failures never raise to the agent loop
        return Result.failure(E_ACTION_FAILED, f"{tool.name} raised {type(exc).__name__}")
    if res.error_code == E_NEEDS_CONFIRM and res.data and "token" in res.data:
        _RESUME_CALLS[res.data["token"]] = (tool, dict(arguments), ctx)
    return res


# ---------------------------------------------------------------------------
# Tool wrappers around the existing services
# ---------------------------------------------------------------------------

def _make_ctx(user_text: str, intent: str) -> dict:
    return {
        "user_text": user_text,
        "intent": intent,
        "allowed_roots": config.get_allowed_roots(),
        "base": Path(config.get("default_work_folder")),
    }


# ---------------------------------------------------------------------------
# Power mode: run_python (restricted sandbox, L2 confirmation every time)
# ---------------------------------------------------------------------------

_BLOCKED_MODULES = {
    "os", "subprocess", "sys", "shutil", "socket", "urllib", "requests",
    "importlib", "ctypes", "multiprocessing", "pathlib", "tempfile", "glob",
    "builtins",
}

_SAFE_BUILTIN_NAMES = (
    "print", "len", "str", "int", "float", "bool",
    "list", "dict", "tuple", "set", "range", "enumerate",
    "zip", "map", "filter", "sorted", "reversed",
    "abs", "max", "min", "sum", "any", "all",
    "isinstance", "type", "repr",
)


def _blocked_import(name, *args, **kwargs):
    """Replace __builtins__.__import__ to refuse dangerous module imports."""
    top = name.split(".")[0]
    if top in _BLOCKED_MODULES:
        raise ImportError(f"Import of '{name}' is not allowed in Power mode.")
    return _builtins_mod.__import__(name, *args, **kwargs)


def _make_workspace_open(workspace: Path):
    """Return an open() callable that only allows paths inside the workspace."""
    def workspace_open(path, mode="r", *args, **kwargs):
        p = Path(path)
        if not p.is_absolute():
            p = workspace / p
        resolved = p.resolve()
        try:
            resolved.relative_to(workspace.resolve())
        except ValueError:
            raise PermissionError(f"Path outside workspace: {path}")
        return open(resolved, mode, *args, **kwargs)
    return workspace_open


def _execute_python(code: str, workspace: Path) -> dict:
    """Execute Python code in a restricted sandbox with a 30 second timeout.

    No shell passthrough (no subprocess). Dangerous module imports are refused.
    File access is restricted to the workspace folder. Returns a dict with
    ``output``, ``error`` and ``timed_out`` keys.
    """
    result = {"output": "", "error": None, "timed_out": False}

    def target():
        try:
            safe_builtins = {
                k: getattr(_builtins_mod, k) for k in _SAFE_BUILTIN_NAMES
            }
            safe_builtins["__import__"] = _blocked_import
            safe_builtins["open"] = _make_workspace_open(workspace)

            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                exec(code, {"__builtins__": safe_builtins}, {})
            result["output"] = out.getvalue()
        except Exception as exc:  # sandbox failures must not escape
            result["error"] = str(exc)

    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout=30)
    if thread.is_alive():
        result["timed_out"] = True
        result["error"] = "Code execution timed out after 30 seconds."

    return result


def _run_python(arguments: dict, ctx: dict) -> Result:
    """Execute Python code inside the workspace only (Power mode, L2 confirmation)."""
    if not config.get_bool("power_mode"):
        return Result.failure(E_BLOCKED, "Power mode is disabled in Settings.")

    code = arguments.get("code", "")
    if not code.strip():
        return Result.failure(E_ACTION_FAILED, "No code to run.")

    workspace = Path(ctx.get("base") or config.get("default_work_folder"))

    def go() -> Result:
        res = _execute_python(code, workspace)
        if res["timed_out"] or res["error"]:
            return Result.failure(E_ACTION_FAILED, res["error"] or "timed out")
        return Result.success({"output": res["output"], "code": code, "workspace": str(workspace)})

    return policy.run_guarded(
        "run_python", code, go,
        user_text=ctx.get("user_text", ""), intent=ctx.get("intent", ""),
        token=ctx.get("token"),
        allowed_roots=ctx.get("allowed_roots"), base=ctx.get("base"),
    )


def _file_create(arguments: dict, ctx: dict) -> Result:
    return files.create(arguments["path"], arguments.get("content", ""), ctx=ctx)


def _file_read(arguments: dict, ctx: dict) -> Result:
    return files.read(arguments["path"], ctx=ctx)


def _file_search(arguments: dict, ctx: dict) -> Result:
    return files.search(arguments["query"], arguments.get("folder"),
                        ctx=ctx)


def _folder_create(arguments: dict, ctx: dict) -> Result:
    return files.create_folder(arguments["folder"], ctx=ctx)


def _file_delete(arguments: dict, ctx: dict) -> Result:
    return files.delete(arguments["path"], ctx=ctx)


def _office_create(arguments: dict, ctx: dict) -> Result:
    kind = arguments.get("kind", "docx")
    name = arguments["name"]
    if kind == "xlsx":
        rows = arguments.get("rows") or [[n] for n in office.INDIAN_NAMES[: arguments.get("count", 5)]]
        return office.create_workbook(name, rows, ctx=ctx)
    return office.create_document(name, [arguments.get("content", "")], ctx=ctx)


def _app_open(arguments: dict, ctx: dict) -> Result:
    return apps.open_app(arguments["app"], ctx=ctx)


def _app_close(arguments: dict, ctx: dict) -> Result:
    return apps.close_app(arguments["app"], ctx=ctx)


def _special_folder_open(arguments: dict, ctx: dict) -> Result:
    return system.open_special_folder(arguments["name"], ctx=ctx)


def _web_open(arguments: dict, ctx: dict) -> Result:
    return system.web_open(arguments["url"], ctx=ctx)


def _screenshot(arguments: dict, ctx: dict) -> Result:
    return system.screenshot(ctx=ctx)


def _system_status(arguments: dict, ctx: dict) -> Result:
    return system.status(ctx=ctx)


def _memory_save(arguments: dict, ctx: dict) -> Result:
    return store.save_fact(arguments["text"])


def _memory_recall(arguments: dict, ctx: dict) -> Result:
    return store.recall(arguments["text"])


def _memory_forget(arguments: dict, ctx: dict) -> Result:
    return store.forget(f"forget my {arguments['attribute']}", ctx=ctx)


def _doc_question(arguments: dict, ctx: dict) -> Result:
    return answerer.answer(arguments["question"])


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

_SCHEMA_COMMON_PATH = {
    "path": {"type": "string", "description": "File path or name (relative to the workspace)."}
}

register(
    "file_create",
    "Create a new text file inside the allowed workspace folder.",
    {
        "type": "object",
        "properties": {
            **_SCHEMA_COMMON_PATH,
            "content": {"type": "string", "description": "Text to write into the file."},
        },
        "required": ["path"],
    },
    1,
    _file_create,
)

register(
    "file_read",
    "Read and return the contents of a file inside the allowed workspace folder.",
    _SCHEMA_COMMON_PATH,
    0,
    _file_read,
)

register(
    "file_search",
    "Search for files whose names contain a query string inside the workspace.",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "File name substring to search for."},
            "folder": {"type": "string",
                       "description": "Folder to search in (defaults to workspace)."},
        },
        "required": ["query"],
    },
    0,
    _file_search,
)

register(
    "folder_create",
    "Create a new folder inside the allowed workspace folder.",
    {
        "type": "object",
        "properties": {
            "folder": {"type": "string", "description": "Folder name or path to create."},
        },
        "required": ["folder"],
    },
    1,
    _folder_create,
)

register(
    "file_delete",
    "Move a file to the Recycle Bin (needs confirmation).",
    _SCHEMA_COMMON_PATH,
    2,
    _file_delete,
)

register(
    "office_create",
    "Create an Excel (.xlsx) or Word (.docx) file inside the workspace.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "File name (with or without extension)."},
            "kind": {"type": "string", "description": "'xlsx' or 'docx'.", "default": "docx"},
            "content": {"type": "string", "description": "Text content for a Word document."},
            "rows": {"type": "array", "description": "Rows for an Excel workbook."},
            "count": {"type": "integer", "description": "Number of example rows (xlsx)."},
        },
        "required": ["name"],
    },
    1,
    _office_create,
)

register(
    "app_open",
    "Launch an allow-listed Windows application by name.",
    {
        "type": "object",
        "properties": {
            "app": {"type": "string",
                    "description": "Application name (e.g. notepad, calculator, chrome, WhatsApp)."},
        },
        "required": ["app"],
    },
    1,
    _app_open,
)

register(
    "app_close",
    "Close an allow-listed application (needs confirmation).",
    {
        "type": "object",
        "properties": {
            "app": {"type": "string", "description": "Application name to close."},
        },
        "required": ["app"],
    },
    2,
    _app_close,
)

register(
    "special_folder_open",
    "Open a Windows special folder (Recycle Bin, Downloads, Documents, Desktop).",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string",
                     "description": "Special folder name (e.g. Recycle Bin, Downloads)."},
        },
        "required": ["name"],
    },
    1,
    _special_folder_open,
)

register(
    "web_open",
    "Open a URL or website in the default browser.",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL or website to open (e.g. youtube.com)."},
        },
        "required": ["url"],
    },
    1,
    _web_open,
)

register(
    "screenshot",
    "Take a screenshot and save it inside the workspace.",
    {"type": "object", "properties": {}, "required": []},
    1,
    _screenshot,
)

register(
    "system_status",
    "Report CPU, memory and disk usage of this computer.",
    {"type": "object", "properties": {}, "required": []},
    0,
    _system_status,
)

register(
    "memory_save",
    "Remember a personal fact (e.g. 'my car is Audi').",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The fact to remember."},
        },
        "required": ["text"],
    },
    1,
    _memory_save,
)

register(
    "memory_recall",
    "Recall a previously remembered personal fact.",
    {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Cue describing the fact to recall."},
        },
        "required": ["text"],
    },
    0,
    _memory_recall,
)

def _volume_control(arguments: dict, ctx: dict) -> Result:
    return audio.control(arguments["op"], arguments.get("device", "speaker"), arguments.get("level"), ctx=ctx)


def _brightness_control(arguments: dict, ctx: dict) -> Result:
    return display.control(arguments["op"], arguments.get("level"), ctx=ctx)


def _levels_read(arguments: dict, ctx: dict) -> Result:
    out = {}
    for device in audio.DEVICES:
        r = audio.read(device)
        out[device] = r.data if r.ok else {"error": r.message}
    b = display.read()
    out["brightness"] = b.data["level"] if b.ok else {"error": b.message}
    return Result.success(out)


register(
    "volume_control",
    "Change the speaker or microphone volume: set a level, turn it up or down, mute or unmute.",
    {
        "type": "object",
        "properties": {
            "op": {"type": "string", "enum": list(audio.OPS), "description": "set, up, down, mute or unmute."},
            "device": {"type": "string", "enum": list(audio.DEVICES), "description": "speaker (default) or mic."},
            "level": {"type": "integer", "minimum": 0, "maximum": 100,
                      "description": "Percent for set; the step for up or down (default 10)."},
        },
        "required": ["op"],
    },
    1,
    _volume_control,
)

register(
    "brightness_control",
    "Change the brightness of the laptop's built-in screen: set a level, or turn it up or down.",
    {
        "type": "object",
        "properties": {
            "op": {"type": "string", "enum": list(display.OPS), "description": "set, up or down."},
            "level": {"type": "integer", "minimum": 0, "maximum": 100,
                      "description": "Percent for set; the step for up or down (default 10)."},
        },
        "required": ["op"],
    },
    1,
    _brightness_control,
)

register(
    "levels_read",
    "Read the current speaker volume, microphone volume and screen brightness (and whether they are muted).",
    {"type": "object", "properties": {}},
    0,
    _levels_read,
)

def _power_status(arguments: dict, ctx: dict) -> Result:
    radios = network.status()
    return Result.success({"battery": power.battery().data, "power_plan": power.power_plan(),
                           "radios": radios.data if radios.ok else {"error": radios.message}})


register(
    "radio_control",
    "Switch Wi-Fi or Bluetooth on or off. Turning a radio off needs the user's confirmation.",
    {
        "type": "object",
        "properties": {
            "radio": {"type": "string", "enum": list(network.RADIOS), "description": "wifi or bluetooth."},
            "on": {"type": "boolean", "description": "true to switch on, false to switch off."},
        },
        "required": ["radio", "on"],
    },
    2,
    lambda arguments, ctx: network.set_radio(arguments["radio"], arguments["on"], ctx=ctx),
)

register(
    "power_action",
    "Lock the PC, put it to sleep, restart or shut it down (restart and shut down wait 60 seconds), or cancel a "
    "scheduled restart or shutdown. Sleep, restart and shut down need the user's confirmation.",
    {
        "type": "object",
        "properties": {"op": {"type": "string", "enum": list(power.OPS),
                              "description": "lock, sleep, restart, shutdown or cancel."}},
        "required": ["op"],
    },
    2,
    lambda arguments, ctx: power.act(arguments["op"], ctx=ctx),
)

register(
    "power_status",
    "Read the battery (percent, charging, minutes left), the power plan, and whether Wi-Fi and Bluetooth are on "
    "(with the connected Wi-Fi network and its signal).",
    {"type": "object", "properties": {}},
    0,
    _power_status,
)

register(
    "window_list",
    "List the open windows (title and app), top-most first.",
    {"type": "object", "properties": {}},
    0,
    lambda arguments, ctx: windows.list_windows(),
)

register(
    "window_control",
    "Focus (switch to), minimize, maximize, restore or politely close one open window, picked by app name or by words "
    "of its title; or minimize_all / restore_all windows. 'close' lets an app with unsaved work ask to save.",
    {
        "type": "object",
        "properties": {
            "op": {"type": "string", "enum": list(windows.OPS)},
            "target": {"type": "string", "description": "App name or title words (not needed for minimize_all / restore_all)."},
        },
        "required": ["op"],
    },
    1,
    lambda arguments, ctx: windows.control(arguments["op"], arguments.get("target", ""), ctx=ctx),
)

register(
    "ask_user",
    "Ask the user one short clarifying question when the request is genuinely ambiguous. The loop pauses and the "
    "user's answer comes back as this tool's result.",
    {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "The question, in the user's language.", "minLength": 1},
            "options": {"type": "array", "items": {"type": "string"}, "description": "Two to four short choices (optional)."},
        },
        "required": ["question"],
    },
    0,
    lambda arguments, ctx: Result.success({"question": arguments["question"], "options": arguments.get("options") or []}),
)

register(
    "memory_forget",
    "Forget (delete) one remembered personal fact. Needs the user's confirmation.",
    {
        "type": "object",
        "properties": {
            "attribute": {"type": "string", "description": "What to forget, e.g. 'locker code' or 'car'."},
        },
        "required": ["attribute"],
    },
    2,
    _memory_forget,
)

register(
    "doc_question",
    "Answer a question from the user's indexed documents (TXT/DOCX).",
    {
        "type": "object",
        "properties": {
            "question": {"type": "string", "description": "Question about the documents."},
        },
        "required": ["question"],
    },
    0,
    _doc_question,
)

register(
    "run_python",
    "Execute Python code inside the workspace only (Power mode, needs confirmation every time).",
    {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python source code to execute."},
        },
        "required": ["code"],
    },
    2,
    _run_python,
)


# ---------------------------------------------------------------------------
# Tools added for the native tool-calling agent (P1)
# ---------------------------------------------------------------------------

def _memory_list(arguments: dict, ctx: dict) -> Result:
    facts = store.list_facts()
    return Result.success({"count": len(facts), "facts": [f["fact"][:300] for f in facts[:20]]})


def _get_time(arguments: dict, ctx: dict) -> Result:
    from datetime import datetime
    now = datetime.now()
    return Result.success({"time": now.strftime("%I:%M %p"), "date": now.strftime("%A %d %B %Y")})


def _set_user_name(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.chat import identity
    name = " ".join(str(arguments.get("name", "")).split())[:60]
    if not name:
        return Result.failure(E_ACTION_FAILED, "No name was given.")
    identity.save_name(name)
    return Result.success({"name": name})


def _voice_control(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import features
    res = features.voice_command(str(arguments.get("action", "")), str(arguments.get("value", "")), ctx=ctx)
    if res.ok:
        return Result.success({**res.data, "voice_cmd": dict(res.data)})
    return res


def _open_page(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import features
    res = features.open_page(str(arguments.get("page", "")), ctx=ctx)
    if res.ok:
        return Result.success({**res.data, "open_page": res.data["page"]})
    return res


def _performance_report(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import features
    return features.perf_report(ctx=ctx)


def _clean_temp_files(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import features
    return features.temp_clean(ctx=ctx, token=ctx.get("token"))


register("memory_list", "List everything the user asked the assistant to remember.", {"type": "object", "properties": {}}, 0, _memory_list)
register("get_time", "Get the current local time and date.", {"type": "object", "properties": {}}, 0, _get_time)
register("set_user_name", "Save the name the user wants to be called.",
         {"type": "object", "properties": {"name": {"type": "string", "description": "The user's name."}}, "required": ["name"]}, 1, _set_user_name)
register("voice_control", "Change voice settings: start or stop hands-free listening, stop speaking, speak replies aloud or not, "
         "wake word on or off, or set the voice language.",
         {"type": "object", "properties": {
             "action": {"type": "string", "enum": ["start", "stop", "quiet", "speak_on", "speak_off", "wake_on", "wake_off", "lang"]},
             "value": {"type": "string", "description": "For action lang: en-IN, hi-IN or gu-IN."}}, "required": ["action"]}, 1, _voice_control)
register("open_page", "Show one of the application's pages: vision (Object Detection) or performance (PC Performance).",
         {"type": "object", "properties": {"page": {"type": "string", "enum": ["vision", "performance"]}}, "required": ["page"]}, 0, _open_page)
register("performance_report", "CPU, RAM and disk use now, plus the applications using the most memory.",
         {"type": "object", "properties": {}}, 0, _performance_report)
register("clean_temp_files", "Delete temporary files older than one day to free disk space (needs confirmation).",
         {"type": "object", "properties": {}}, 2, _clean_temp_files)


# ---------------------------------------------------------------------------
# Notebook tools (P2)
# ---------------------------------------------------------------------------

def _source_list(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.rag import sources
    return sources.list_sources(ctx=ctx)


def _source_summary(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.rag import sources
    return sources.summarize(arguments.get("name") or None, ctx=ctx)


def _source_delete(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.rag import sources
    return sources.delete_source(str(arguments.get("name", "")), ctx=ctx, token=ctx.get("token"))


def _notebook_list(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.rag import sources
    return Result.success({"active": sources.active()["name"],
                           "notebooks": [{"name": n["name"], "sources": n["sources"]} for n in sources.list_notebooks()]})


def _notebook_open(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.rag import sources
    name = str(arguments.get("name", ""))
    found = sources.find_notebook(name)
    if found:
        sources.set_active(found["id"])
        return Result.success({"name": found["name"], "created": False})
    res = sources.create_notebook(name)
    return Result.success({"name": res.data["name"], "created": True}) if res.ok else res


register("source_list", "List the sources (documents) in the active notebook.", {"type": "object", "properties": {}}, 0, _source_list)
register("source_summary", "Summarise one source by file name, or every source in the active notebook when no name is given.",
         {"type": "object", "properties": {"name": {"type": "string", "description": "File name of the source (optional)."}}}, 0, _source_summary)
register("source_delete", "Remove one source from the active notebook (needs confirmation).",
         {"type": "object", "properties": {"name": {"type": "string", "description": "File name of the source."}}, "required": ["name"]}, 2, _source_delete)
register("notebook_list", "List notebooks and show which one is active.", {"type": "object", "properties": {}}, 0, _notebook_list)
register("notebook_open", "Switch to a notebook by name, creating it if it does not exist. New attachments and document questions use it.",
         {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]}, 1, _notebook_open)


# ---------------------------------------------------------------------------
# Cowork tools (P4): processes, reminders, clipboard
# ---------------------------------------------------------------------------

def _process_list(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import processes
    return processes.list_processes(int(arguments.get("top") or 10), str(arguments.get("sort") or "memory"), ctx=ctx)


def _process_kill(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import processes
    return processes.kill_process(str(arguments.get("target", "")), ctx=ctx, token=ctx.get("token"))


def _reminder_add(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import reminders, when
    text = str(arguments.get("text") or "Reminder")
    w = when.parse(str(arguments.get("when") or ""))
    if w.due is None:
        return Result.failure(E_ACTION_FAILED, "I could not understand the time. Use words like 'at 6 pm', 'in 20 minutes' or 'tomorrow 9 am'.")
    return reminders.add(text, w.due.strftime(reminders.FMT), "daily" if (w.repeat == "daily" or arguments.get("daily")) else "none", ctx=ctx)


def _reminder_list(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import reminders
    return reminders.list_pending(ctx=ctx)


def _reminder_cancel(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import reminders
    return reminders.cancel(str(arguments.get("query") or ""), all_pending=bool(arguments.get("all")), ctx=ctx, token=ctx.get("token"))


def _clipboard_read(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import clipboard
    return clipboard.read(ctx=ctx)


def _clipboard_write(arguments: dict, ctx: dict) -> Result:
    from adhyaksh.tools import clipboard
    return clipboard.write(str(arguments.get("text", "")), ctx=ctx)


register("process_list", "List the programs using the most memory (or CPU) right now.",
         {"type": "object", "properties": {"top": {"type": "integer", "description": "How many programs (1-30)."},
                                           "sort": {"type": "string", "enum": ["memory", "cpu"]}}}, 0, _process_list)
register("process_kill", "End a running program by name or process id (needs confirmation; system processes are refused).",
         {"type": "object", "properties": {"target": {"type": "string", "description": "Program name (e.g. chrome.exe), process id, or 'heaviest'."}},
          "required": ["target"]}, 2, _process_kill)
register("reminder_add", "Set a reminder or alarm.",
         {"type": "object", "properties": {"text": {"type": "string", "description": "What to remind about."},
                                           "when": {"type": "string", "description": "Time in words, e.g. 'at 6 pm', 'in 20 minutes', 'tomorrow 9 am', 'every day at 8 pm'."},
                                           "daily": {"type": "boolean"}}, "required": ["text", "when"]}, 1, _reminder_add)
register("reminder_list", "List pending reminders.", {"type": "object", "properties": {}}, 0, _reminder_list)
register("reminder_cancel", "Cancel one reminder by a word from it, or all reminders (all needs confirmation).",
         {"type": "object", "properties": {"query": {"type": "string"}, "all": {"type": "boolean"}}}, 1, _reminder_cancel)
register("clipboard_read", "Read the text currently on the clipboard.", {"type": "object", "properties": {}}, 0, _clipboard_read)
register("clipboard_write", "Copy text to the clipboard.",
         {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}, 1, _clipboard_write)

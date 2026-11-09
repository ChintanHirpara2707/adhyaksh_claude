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
from adhyaksh.result import E_ACTION_FAILED, E_BLOCKED, E_NEEDS_CONFIRM, Result
from adhyaksh.rag import answerer
from adhyaksh.safety import policy
from adhyaksh.tools import apps, files, office, system

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


def schemas() -> list[dict]:
    """OpenAI-style function schemas describing every registered tool.

    ``run_python`` is omitted unless Power mode is enabled in Settings.
    """
    include_power = config.get_bool("power_mode")
    return [
        {"name": t.name, "description": t.description, "parameters": t.parameters}
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


def _doc_question(arguments: dict, ctx: dict) -> Result:
    return answerer.answer(arguments["question"])


def _web_search(arguments: dict, ctx: dict) -> Result:
    return system.web_search(arguments["query"], ctx=ctx)


def _fetch_page(arguments: dict, ctx: dict) -> Result:
    return system.fetch_page(arguments["url"], ctx=ctx)


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
    "web_search",
    "Search the web and return a list of results (title, URL, snippet).",
    {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
        },
        "required": ["query"],
    },
    0,
    _web_search,
)

register(
    "fetch_page",
    "Fetch a webpage and return its cleaned text content. L0 read-only.",
    {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch (http/https only)."},
        },
        "required": ["url"],
    },
    0,
    _fetch_page,
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

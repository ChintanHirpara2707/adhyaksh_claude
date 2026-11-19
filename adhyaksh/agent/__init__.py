"""Agent package: the tool registry and the tool-calling loop.

Public entry points: :func:`adhyaksh.agent.native.run` and :func:`adhyaksh.agent.native.resume`.
Model turns go through :mod:`adhyaksh.llm.toolcall` (native tool calls or the JSON protocol).
"""
from adhyaksh.agent import registry  # noqa: F401
from adhyaksh.agent.native import MAX_STEPS, TIMEOUT, resume, run  # noqa: F401

__all__ = ["MAX_STEPS", "TIMEOUT", "run", "resume", "registry"]

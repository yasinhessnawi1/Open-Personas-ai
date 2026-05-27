"""Tool / MCP domain exceptions — re-exports from :mod:`persona.errors`.

Keeping the canonical definitions in ``persona.errors`` means audit-log
consumers and ``isinstance(e, PersonaError)`` checks continue to work without
importing from this module. This module exists for ergonomics:
``from persona.tools.errors import ToolNotAllowedError`` reads naturally.

See spec 03 D-03-1 for the flat (no intermediate ``MCPError`` parent) design.
"""

from __future__ import annotations

from persona.errors import (
    MCPConnectionError,
    MCPServerUnavailableError,
    SandboxViolationError,
    ToolExecutionError,
    ToolNotAllowedError,
)

__all__ = [
    "MCPConnectionError",
    "MCPServerUnavailableError",
    "SandboxViolationError",
    "ToolExecutionError",
    "ToolNotAllowedError",
]

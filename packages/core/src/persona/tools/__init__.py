"""``persona.tools`` — spec 03 surface.

Tool protocols, the ``@tool`` decorator, Toolbox, provider-aware
result formatting, the four built-in tools, MCP client + adapter,
and the tool-audit Protocol.

Engineering standards §1.1 ("smallest public API surface") — only
the names that downstream specs (5/6/8) need are re-exported here.
"""

from __future__ import annotations

from persona.tools._factory import build_default_toolbox
from persona.tools.audit import (
    JSONLToolAuditLogger,
    MemoryToolAuditLogger,
    ToolAuditEvent,
    ToolAuditLogger,
)
from persona.tools.builtin.file_read import make_file_read_tool
from persona.tools.builtin.file_write import make_file_write_tool
from persona.tools.builtin.web_fetch import make_web_fetch_tool
from persona.tools.builtin.web_search import make_web_search_tool
from persona.tools.errors import (
    MCPConnectionError,
    MCPServerUnavailableError,
    SandboxViolationError,
    ToolExecutionError,
    ToolNotAllowedError,
)
from persona.tools.formatting import format_tool_result
from persona.tools.mcp.adapter import MCPToolAdapter
from persona.tools.mcp.client import MCPClient, load_mcp_clients
from persona.tools.protocol import AsyncTool, ToolDescriptor, tool
from persona.tools.toolbox import Toolbox

__all__ = [
    # Protocols + decorator
    "AsyncTool",
    "JSONLToolAuditLogger",
    # MCP
    "MCPClient",
    "MCPConnectionError",
    "MCPServerUnavailableError",
    "MCPToolAdapter",
    "MemoryToolAuditLogger",
    # Errors
    "SandboxViolationError",
    "ToolAuditEvent",
    "ToolAuditLogger",
    "ToolDescriptor",
    "ToolExecutionError",
    "ToolNotAllowedError",
    # Registry
    "Toolbox",
    # Factory + composer
    "build_default_toolbox",
    "format_tool_result",
    "load_mcp_clients",
    "make_file_read_tool",
    "make_file_write_tool",
    "make_web_fetch_tool",
    "make_web_search_tool",
    "tool",
]

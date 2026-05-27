"""MCP tool adapter — wraps an MCP server tool as an :class:`AsyncTool`.

Per spec §7.2 and D-03-19, each MCP-discovered tool becomes an
:class:`AsyncTool` named ``mcp:{server_name}:{tool_name}`` so the
Toolbox's literal allow-list (Phase 1 refinement #4) handles it
unambiguously.

The adapter calls ``ClientSession.call_tool(name, arguments=kwargs)``
on the underlying MCP session and maps the result to
:class:`ToolResult`. If the connection dies mid-call, the adapter
returns ``ToolResult(is_error=True, content="MCP server disconnected")``
per spec §7.3 — no exception escapes.

Per-call dispatch audits are skipped per D-03-21. The lifecycle
events (connect / disconnect / server_unavailable) are emitted by
:class:`persona.tools.mcp.client.MCPClient`, not the adapter.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from persona.logging import get_logger
from persona.schema.tools import ToolResult

if TYPE_CHECKING:
    from mcp import ClientSession
    from mcp.types import Tool as MCPToolDef

__all__ = ["MCPToolAdapter"]

_logger = get_logger("tools.mcp.adapter")


class MCPToolAdapter:
    """Wraps a single MCP server tool as an :class:`AsyncTool`.

    Attributes are class-stamped (not properties) so the structural
    Protocol check (``isinstance(obj, AsyncTool)``) sees them.

    Args:
        server_name: The MCP server identifier (config key); the
            ``mcp:<server>:`` prefix in the resulting tool name.
        session: The active :class:`mcp.ClientSession`. Lifecycle is
            managed by :class:`MCPClient`; the adapter only holds a
            reference and never opens/closes the session.
        tool_def: The :class:`mcp.types.Tool` returned by ``list_tools``.
    """

    def __init__(
        self,
        *,
        server_name: str,
        session: ClientSession,
        tool_def: MCPToolDef,
    ) -> None:
        self._server_name = server_name
        self._session = session
        self._mcp_tool_name = tool_def.name

        # Stamp the AsyncTool surface as instance attributes — Protocols
        # accept either properties or plain attributes.
        self.name = f"mcp:{server_name}:{tool_def.name}"
        self.description = tool_def.description or ""
        # MCP gives us a JSON-Schema dict (`inputSchema`). Anthropic + OpenAI
        # accept this dialect directly (research §3.5 / §4.2).
        self.parameters_schema: dict[str, Any] = dict(tool_def.inputSchema or {})

    async def execute(self, **kwargs: Any) -> ToolResult:  # noqa: ANN401
        try:
            result = await self._session.call_tool(self._mcp_tool_name, arguments=kwargs)
        except Exception as e:  # noqa: BLE001 — broad envelope; tool never raises
            # Includes connection-died errors from the SDK (anyio.EndOfStream,
            # ClosedResourceError, httpx.HTTPError) — all become a graceful
            # ToolResult per spec §7.3.
            _logger.warning(
                "mcp tool call failed",
                server=self._server_name,
                tool=self._mcp_tool_name,
                error=type(e).__name__,
            )
            err_type = type(e).__name__
            msg = str(e) or ""
            # Disconnection-like errors get the canonical message.
            disconnect_markers = ("ClosedResource", "EndOfStream", "Disconnect")
            if any(marker in err_type for marker in disconnect_markers):
                return ToolResult(
                    tool_name=self.name,
                    content="MCP server disconnected",
                    is_error=True,
                )
            return ToolResult(
                tool_name=self.name,
                content=f"{err_type}: {msg}",
                is_error=True,
            )

        # Aggregate text content from the result. MCP returns a list of
        # content blocks (TextContent, ImageContent, etc.); we concatenate
        # the text content for ToolResult.content and surface structured
        # content via ToolResult.data when present.
        text_parts: list[str] = []
        for block in result.content or []:
            text = getattr(block, "text", None)
            if isinstance(text, str):
                text_parts.append(text)

        content = "\n".join(text_parts) if text_parts else ""
        data: dict[str, Any] | None = None
        structured = getattr(result, "structuredContent", None)
        if structured:
            data = dict(structured) if isinstance(structured, dict) else {"value": structured}

        return ToolResult(
            tool_name=self.name,
            content=content,
            data=data,
            is_error=bool(getattr(result, "isError", False)),
        )

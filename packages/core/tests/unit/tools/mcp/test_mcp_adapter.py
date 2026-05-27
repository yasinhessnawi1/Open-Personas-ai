"""Tests for the MCPToolAdapter wrapper (T11)."""

# ruff: noqa: ANN401, ARG001, ARG002, ERA001, SLF001
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from persona.tools.mcp.adapter import MCPToolAdapter
from persona.tools.protocol import AsyncTool, ToolDescriptor


def _mcp_tool_def(
    *,
    name: str = "search",
    description: str = "Search the case database.",
    input_schema: dict[str, Any] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=description,
        inputSchema=input_schema or {"type": "object", "properties": {"q": {"type": "string"}}},
    )


def _mcp_call_result(
    *,
    text: str | None = "ok",
    is_error: bool = False,
    structured: dict[str, Any] | None = None,
) -> SimpleNamespace:
    content_blocks = []
    if text is not None:
        content_blocks.append(SimpleNamespace(text=text, type="text"))
    return SimpleNamespace(
        content=content_blocks,
        isError=is_error,
        structuredContent=structured,
    )


# Section: AsyncTool surface


class TestAdapterSurface:
    def test_satisfies_async_tool(self) -> None:
        session = SimpleNamespace(call_tool=AsyncMock())
        adapter = MCPToolAdapter(
            server_name="legal-db",
            session=session,
            tool_def=_mcp_tool_def(),
        )
        assert isinstance(adapter, AsyncTool)
        assert isinstance(adapter, ToolDescriptor)

    def test_name_format_uses_mcp_prefix(self) -> None:
        session = SimpleNamespace(call_tool=AsyncMock())
        adapter = MCPToolAdapter(
            server_name="husleietvistutvalget",
            session=session,
            tool_def=_mcp_tool_def(name="search_cases"),
        )
        assert adapter.name == "mcp:husleietvistutvalget:search_cases"

    def test_description_and_schema_propagate(self) -> None:
        session = SimpleNamespace(call_tool=AsyncMock())
        schema = {"type": "object", "properties": {"a": {"type": "integer"}}, "required": ["a"]}
        adapter = MCPToolAdapter(
            server_name="srv",
            session=session,
            tool_def=_mcp_tool_def(description="Looks stuff up.", input_schema=schema),
        )
        assert adapter.description == "Looks stuff up."
        assert adapter.parameters_schema == schema

    def test_handles_missing_description(self) -> None:
        session = SimpleNamespace(call_tool=AsyncMock())
        adapter = MCPToolAdapter(
            server_name="srv",
            session=session,
            tool_def=SimpleNamespace(
                name="x",
                description=None,
                inputSchema={"type": "object"},
            ),
        )
        assert adapter.description == ""


# Section: execute - happy path


class TestAdapterExecuteHappy:
    @pytest.mark.asyncio
    async def test_calls_mcp_session_with_arguments(self) -> None:
        call_tool = AsyncMock(return_value=_mcp_call_result(text="42 cases"))
        session = SimpleNamespace(call_tool=call_tool)
        adapter = MCPToolAdapter(
            server_name="legal",
            session=session,
            tool_def=_mcp_tool_def(name="search"),
        )
        result = await adapter.execute(q="rent dispute")
        # Verify SDK invocation.
        call_tool.assert_awaited_once_with("search", arguments={"q": "rent dispute"})
        # Verify ToolResult shape.
        assert result.is_error is False
        assert result.content == "42 cases"
        assert result.tool_name == "mcp:legal:search"

    @pytest.mark.asyncio
    async def test_concatenates_text_blocks(self) -> None:
        # MCP may return multiple text-content blocks; we join them.
        session = SimpleNamespace(
            call_tool=AsyncMock(
                return_value=SimpleNamespace(
                    content=[
                        SimpleNamespace(text="line 1", type="text"),
                        SimpleNamespace(text="line 2", type="text"),
                    ],
                    isError=False,
                    structuredContent=None,
                )
            )
        )
        adapter = MCPToolAdapter(
            server_name="srv",
            session=session,
            tool_def=_mcp_tool_def(),
        )
        result = await adapter.execute()
        assert result.content == "line 1\nline 2"

    @pytest.mark.asyncio
    async def test_structured_content_lands_in_data(self) -> None:
        session = SimpleNamespace(
            call_tool=AsyncMock(
                return_value=_mcp_call_result(
                    text="summary",
                    structured={"cases": [{"id": 1, "title": "Tenant v. Landlord"}]},
                )
            )
        )
        adapter = MCPToolAdapter(
            server_name="legal",
            session=session,
            tool_def=_mcp_tool_def(),
        )
        result = await adapter.execute(q="x")
        assert result.data is not None
        assert result.data["cases"][0]["title"] == "Tenant v. Landlord"

    @pytest.mark.asyncio
    async def test_empty_content_returns_empty_string(self) -> None:
        session = SimpleNamespace(
            call_tool=AsyncMock(
                return_value=SimpleNamespace(
                    content=[],
                    isError=False,
                    structuredContent=None,
                )
            )
        )
        adapter = MCPToolAdapter(
            server_name="srv",
            session=session,
            tool_def=_mcp_tool_def(),
        )
        result = await adapter.execute()
        assert result.is_error is False
        assert result.content == ""


# Section: execute - error paths


class TestAdapterExecuteErrors:
    @pytest.mark.asyncio
    async def test_is_error_flag_propagates(self) -> None:
        # MCP server returned a result block marked isError=True (e.g., the
        # tool itself reported a failure but the protocol round-trip worked).
        session = SimpleNamespace(
            call_tool=AsyncMock(
                return_value=_mcp_call_result(text="tool failed inside server", is_error=True)
            )
        )
        adapter = MCPToolAdapter(
            server_name="srv",
            session=session,
            tool_def=_mcp_tool_def(),
        )
        result = await adapter.execute()
        assert result.is_error is True
        assert "tool failed" in result.content

    @pytest.mark.asyncio
    async def test_disconnection_returns_clean_error(self) -> None:
        # SDK closed-resource error → ToolResult(is_error=True, content="MCP server disconnected").
        class ClosedResourceError(Exception):
            pass

        session = SimpleNamespace(call_tool=AsyncMock(side_effect=ClosedResourceError("closed")))
        adapter = MCPToolAdapter(
            server_name="srv",
            session=session,
            tool_def=_mcp_tool_def(),
        )
        result = await adapter.execute()
        assert result.is_error is True
        assert "disconnected" in result.content

    @pytest.mark.asyncio
    async def test_generic_error_returns_envelope(self) -> None:
        session = SimpleNamespace(call_tool=AsyncMock(side_effect=RuntimeError("boom")))
        adapter = MCPToolAdapter(
            server_name="srv",
            session=session,
            tool_def=_mcp_tool_def(),
        )
        result = await adapter.execute()
        assert result.is_error is True
        assert "RuntimeError" in result.content
        assert "boom" in result.content

    @pytest.mark.asyncio
    async def test_no_exception_escapes(self) -> None:
        # The adapter must NEVER raise — even on the strangest SDK output.
        session = SimpleNamespace(call_tool=AsyncMock(side_effect=KeyError("missing key")))
        adapter = MCPToolAdapter(
            server_name="srv",
            session=session,
            tool_def=_mcp_tool_def(),
        )
        result = await adapter.execute(x="y")
        assert result.is_error is True
        # KeyError stringifies to the key in quotes; check we have something.
        assert result.content

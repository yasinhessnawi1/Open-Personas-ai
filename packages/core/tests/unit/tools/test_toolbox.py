"""Tests for the Toolbox registry, allow-list, and dispatch (T06)."""

# ruff: noqa: ANN401, ARG001, ARG002, ERA001
from __future__ import annotations

import pytest
from persona.errors import ToolExecutionError, ToolNotAllowedError
from persona.schema.tools import ToolCall, ToolResult
from persona.tools.protocol import AsyncTool, tool
from persona.tools.toolbox import Toolbox

# ---------------------------------------------------------------------------
# Section: fixtures — small @tool-decorated helpers
# ---------------------------------------------------------------------------


def _make_echo_tool(name: str = "echo") -> AsyncTool:
    @tool(name=name, description=f"Echo for {name}")
    async def _echo(text: str) -> ToolResult:
        return ToolResult(tool_name=name, content=text)

    return _echo


def _make_adder_tool() -> AsyncTool:
    @tool(name="adder", description="Add two ints.")
    async def _adder(a: int, b: int) -> ToolResult:
        return ToolResult(tool_name="adder", content=str(a + b))

    return _adder


# ---------------------------------------------------------------------------
# Section: construction
# ---------------------------------------------------------------------------


class TestConstruction:
    def test_registers_unique_names(self) -> None:
        tb = Toolbox([_make_echo_tool("a"), _make_echo_tool("b")], allow_list=["a", "b"])
        assert tb.names() == ["a", "b"]

    def test_duplicate_name_raises(self) -> None:
        with pytest.raises(ValueError, match="duplicate"):
            Toolbox([_make_echo_tool("dup"), _make_echo_tool("dup")])

    def test_allow_list_none_is_permissive(self) -> None:
        tb = Toolbox([_make_echo_tool("x"), _make_echo_tool("y")])
        assert tb.is_allowed("x") is True
        assert tb.is_allowed("y") is True
        # Even an unregistered name returns True under None — but dispatch
        # will fail with ToolExecutionError because there's no implementation.
        assert tb.is_allowed("unregistered") is True

    def test_allow_list_literal_only(self) -> None:
        tb = Toolbox(
            [_make_echo_tool("web_search"), _make_echo_tool("file_read")],
            allow_list=["web_search"],
        )
        assert tb.is_allowed("web_search") is True
        assert tb.is_allowed("file_read") is False
        # No wildcard semantics — mcp:server:tool entries must be exact (verified
        # via the name-list contents, not pattern matching).
        assert tb.is_allowed("mcp:any:*") is False

    def test_names_under_none_returns_all_registered(self) -> None:
        tb = Toolbox([_make_echo_tool("a"), _make_echo_tool("b")])
        assert tb.names() == ["a", "b"]

    def test_names_under_allow_list_returns_intersection(self) -> None:
        tb = Toolbox(
            [_make_echo_tool("a"), _make_echo_tool("b"), _make_echo_tool("c")],
            allow_list=["b", "c", "x_not_registered"],
        )
        # Sorted intersection of registered ∩ allowed.
        assert tb.names() == ["b", "c"]


# ---------------------------------------------------------------------------
# Section: get_specs
# ---------------------------------------------------------------------------


class TestGetSpecs:
    def test_specs_only_for_allowed_tools(self) -> None:
        tb = Toolbox(
            [_make_echo_tool("a"), _make_echo_tool("b")],
            allow_list=["a"],
        )
        specs = tb.get_specs()
        assert len(specs) == 1
        assert specs[0].name == "a"
        assert specs[0].description == "Echo for a"
        # The synthesised schema includes `text` (the @tool arg).
        assert "text" in specs[0].parameters["properties"]

    def test_specs_empty_when_allow_list_empty(self) -> None:
        tb = Toolbox([_make_echo_tool("a")], allow_list=[])
        assert tb.get_specs() == []


# ---------------------------------------------------------------------------
# Section: dispatch
# ---------------------------------------------------------------------------


class TestDispatch:
    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        tb = Toolbox([_make_echo_tool("echo")], allow_list=["echo"])
        result = await tb.dispatch(ToolCall(name="echo", args={"text": "hi"}, call_id="c1"))
        assert result.tool_name == "echo"
        assert result.content == "hi"
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_not_in_allow_list_raises_tool_not_allowed(self) -> None:
        tb = Toolbox(
            [_make_echo_tool("echo"), _make_adder_tool()],
            allow_list=["echo"],
        )
        with pytest.raises(ToolNotAllowedError) as exc_info:
            await tb.dispatch(ToolCall(name="adder", args={"a": 1, "b": 2}))
        # D-03-8: context["allowed"] is comma-joined string with available tools.
        assert exc_info.value.context["called"] == "adder"
        assert "echo" in exc_info.value.context["allowed"]
        assert "adder" not in exc_info.value.context["allowed"]

    @pytest.mark.asyncio
    async def test_hallucinated_tool_name(self) -> None:
        tb = Toolbox([_make_echo_tool("echo")], allow_list=["echo"])
        with pytest.raises(ToolNotAllowedError) as exc_info:
            await tb.dispatch(ToolCall(name="get_weather", args={"city": "Oslo"}))
        assert exc_info.value.context["called"] == "get_weather"
        # The error message contains the allowed names so the runtime can feed
        # it back to the model.
        assert "echo" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_allowed_but_not_registered_raises_tool_execution(self) -> None:
        # allow_list grants 'web_fetch' but it's not registered.
        tb = Toolbox([_make_echo_tool("echo")], allow_list=["echo", "web_fetch"])
        with pytest.raises(ToolExecutionError) as exc_info:
            await tb.dispatch(ToolCall(name="web_fetch", args={"url": "https://x"}))
        assert exc_info.value.context["name"] == "web_fetch"
        assert exc_info.value.context["reason"] == "not_registered"

    @pytest.mark.asyncio
    async def test_tool_returns_error_result_passed_through(self) -> None:
        # The @tool decorator wraps body exceptions; toolbox doesn't re-wrap.
        @tool(name="boomer", description="d")
        async def boomer(q: str) -> ToolResult:
            raise ValueError("bang")

        tb = Toolbox([boomer], allow_list=["boomer"])
        result = await tb.dispatch(ToolCall(name="boomer", args={"q": "x"}))
        assert result.is_error is True
        assert "ValueError" in result.content

    @pytest.mark.asyncio
    async def test_allow_list_none_permits_dispatch(self) -> None:
        tb = Toolbox([_make_echo_tool("echo")])
        result = await tb.dispatch(ToolCall(name="echo", args={"text": "hi"}))
        assert result.content == "hi"

    @pytest.mark.asyncio
    async def test_dispatch_passes_args_correctly(self) -> None:
        tb = Toolbox([_make_adder_tool()], allow_list=["adder"])
        result = await tb.dispatch(ToolCall(name="adder", args={"a": 3, "b": 4}, call_id="c"))
        assert result.content == "7"


# ---------------------------------------------------------------------------
# Section: MCP-namespaced tool names
# ---------------------------------------------------------------------------


class TestMCPNamespacedNames:
    """MCP tool names use the literal `mcp:server:tool` form (no wildcards)."""

    @pytest.mark.asyncio
    async def test_literal_mcp_name_in_allow_list(self) -> None:
        # Simulate an MCP-discovered tool name.
        @tool(name="mcp:husleietvistutvalget:search", description="MCP test.")
        async def mcp_search(q: str) -> ToolResult:
            return ToolResult(tool_name="mcp:husleietvistutvalget:search", content=q)

        tb = Toolbox(
            [mcp_search, _make_echo_tool("echo")],
            allow_list=["mcp:husleietvistutvalget:search"],
        )
        # The MCP name is allowed; the local 'echo' is not.
        assert tb.is_allowed("mcp:husleietvistutvalget:search") is True
        assert tb.is_allowed("echo") is False

        result = await tb.dispatch(
            ToolCall(name="mcp:husleietvistutvalget:search", args={"q": "rent"})
        )
        assert result.content == "rent"

    def test_no_wildcard_matching(self) -> None:
        @tool(name="mcp:srv:tool_a", description="d")
        async def t_a() -> ToolResult:
            return ToolResult(tool_name="mcp:srv:tool_a", content="ok")

        @tool(name="mcp:srv:tool_b", description="d")
        async def t_b() -> ToolResult:
            return ToolResult(tool_name="mcp:srv:tool_b", content="ok")

        tb = Toolbox([t_a, t_b], allow_list=["mcp:srv:*"])
        # Wildcards are NOT expanded — literal-only allow-list (Phase 1 refinement #4).
        assert tb.is_allowed("mcp:srv:tool_a") is False
        assert tb.is_allowed("mcp:srv:tool_b") is False
        assert tb.is_allowed("mcp:srv:*") is True  # the literal wildcard string
        # And nothing usable is exposed via get_specs.
        assert tb.get_specs() == []

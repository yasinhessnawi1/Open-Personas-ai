"""Parametrised contract tests for built-in tools (T06 skeleton, expanded by T07/T08/T10/T11).

Verifies every tool that lands in :mod:`persona.tools.builtin` (and MCP
adapters in T11) satisfies the :class:`AsyncTool` Protocol and the
no-raise contract (D-03-5).

Tools are added to the ``BUILTIN_TOOL_FACTORIES`` parametrisation as they
land. T06 ships with the @tool-decorator echo-style smoke test only.
"""

# ruff: noqa: ANN401, ARG001, ARG002, ERA001
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from persona.schema.tools import ToolResult
from persona.tools.protocol import AsyncTool, ToolDescriptor, tool

if TYPE_CHECKING:
    from collections.abc import Callable


def _echo_factory() -> AsyncTool:
    @tool(name="echo", description="Echo the text argument.")
    async def echo(text: str) -> ToolResult:
        return ToolResult(tool_name="echo", content=text)

    return echo


# Each entry: (display_name, factory). Built-in tools (T07/T08/T10) and the
# MCP adapter (T11) append to this list as they land.
BUILTIN_TOOL_FACTORIES: list[tuple[str, Callable[[], AsyncTool]]] = [
    ("echo", _echo_factory),
]


@pytest.mark.parametrize(
    "factory",
    [pytest.param(f, id=name) for name, f in BUILTIN_TOOL_FACTORIES],
)
class TestToolContract:
    """Every registered tool factory MUST produce an AsyncTool."""

    def test_factory_returns_async_tool(self, factory: Callable[[], AsyncTool]) -> None:
        instance = factory()
        assert isinstance(instance, AsyncTool)
        assert isinstance(instance, ToolDescriptor)

    def test_factory_returns_independent_instances(self, factory: Callable[[], AsyncTool]) -> None:
        a = factory()
        b = factory()
        # Both satisfy the Protocol; we don't assert identity (some factories
        # may legitimately return module-level singletons).
        assert isinstance(a, AsyncTool)
        assert isinstance(b, AsyncTool)

    def test_has_nonempty_metadata(self, factory: Callable[[], AsyncTool]) -> None:
        instance = factory()
        assert instance.name  # nonempty
        assert instance.description  # nonempty
        assert isinstance(instance.parameters_schema, dict)

"""Tests for the @tool decorator (T04).

Covers:
- JSON-Schema generation from typed `async def` signatures (D-03-4).
- Argument-validation error path (D-03-5).
- Function-body exception envelope (D-03-5).
- `AsyncTool` / `ToolDescriptor` Protocol conformance of decorated objects.
- Non-async decoration rejected.
"""

# ruff: noqa: ANN401, ARG001, ARG002, ERA001 — mock fixtures; "# Section:" markers
from __future__ import annotations

from typing import Any, Literal

import pytest
from persona.errors import PersonaError, SandboxViolationError
from persona.schema.tools import ToolResult
from persona.tools.protocol import AsyncTool, ToolDescriptor, tool

# ---------------------------------------------------------------------------
# Section: JSON Schema generation
# ---------------------------------------------------------------------------


class TestSchemaGeneration:
    """The decorator synthesises parameters_schema from the signature."""

    def test_simple_signature(self) -> None:
        @tool(name="web_search", description="Search the web.")
        async def web_search(query: str, max_results: int = 5) -> ToolResult:
            return ToolResult(tool_name="web_search", content=f"q={query} n={max_results}")

        schema = web_search.parameters_schema
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"
        assert schema["properties"]["max_results"]["type"] == "integer"
        assert schema["properties"]["max_results"]["default"] == 5
        assert schema["required"] == ["query"]

    def test_literal_becomes_enum(self) -> None:
        @tool(name="modal", description="Pick a mode.")
        async def modal(mode: Literal["fast", "thorough"] = "fast") -> ToolResult:
            return ToolResult(tool_name="modal", content=mode)

        schema = modal.parameters_schema
        assert schema["properties"]["mode"]["enum"] == ["fast", "thorough"]
        assert schema["properties"]["mode"]["default"] == "fast"

    def test_optional_field_becomes_anyof_null(self) -> None:
        @tool(name="optish", description="Optional limit.")
        async def optish(limit: int | None = None) -> ToolResult:
            return ToolResult(tool_name="optish", content=str(limit))

        schema = optish.parameters_schema
        prop = schema["properties"]["limit"]
        assert "anyOf" in prop
        types = {opt.get("type") for opt in prop["anyOf"]}
        assert types == {"integer", "null"}

    def test_list_field(self) -> None:
        @tool(name="tagger", description="Apply tags.")
        async def tagger(tags: list[str]) -> ToolResult:
            return ToolResult(tool_name="tagger", content=",".join(tags))

        schema = tagger.parameters_schema
        assert schema["properties"]["tags"]["type"] == "array"
        assert schema["properties"]["tags"]["items"]["type"] == "string"
        assert schema["required"] == ["tags"]

    def test_schema_returned_as_copy(self) -> None:
        @tool(name="x", description="d")
        async def fn(q: str) -> ToolResult:
            return ToolResult(tool_name="x", content=q)

        s1 = fn.parameters_schema
        s2 = fn.parameters_schema
        s1["mutation"] = "should not leak"
        assert "mutation" not in s2


# ---------------------------------------------------------------------------
# Section: Protocol conformance
# ---------------------------------------------------------------------------


class TestProtocolConformance:
    """Decorated objects satisfy AsyncTool (and transitively ToolDescriptor)."""

    def test_is_async_tool(self) -> None:
        @tool(name="x", description="d")
        async def fn(q: str) -> ToolResult:
            return ToolResult(tool_name="x", content=q)

        assert isinstance(fn, AsyncTool)
        assert isinstance(fn, ToolDescriptor)

    def test_name_and_description_propagate(self) -> None:
        @tool(name="my_tool", description="A custom one-liner.")
        async def fn() -> ToolResult:
            return ToolResult(tool_name="my_tool", content="ok")

        assert fn.name == "my_tool"
        assert fn.description == "A custom one-liner."


# ---------------------------------------------------------------------------
# Section: Successful execution
# ---------------------------------------------------------------------------


class TestSuccessfulExecution:
    """The body's ToolResult passes through unchanged."""

    @pytest.mark.asyncio
    async def test_happy_path(self) -> None:
        @tool(name="echo", description="Echo text.")
        async def echo(text: str) -> ToolResult:
            return ToolResult(tool_name="echo", content=text)

        result = await echo.execute(text="hello")
        assert result.tool_name == "echo"
        assert result.content == "hello"
        assert result.is_error is False

    @pytest.mark.asyncio
    async def test_uses_defaults(self) -> None:
        @tool(name="adder", description="Add an offset.")
        async def adder(x: int, offset: int = 10) -> ToolResult:
            return ToolResult(tool_name="adder", content=str(x + offset))

        result = await adder.execute(x=5)
        assert result.content == "15"

    @pytest.mark.asyncio
    async def test_data_and_truncated_fields_pass_through(self) -> None:
        @tool(name="search", description="Mock search.")
        async def search(q: str) -> ToolResult:
            return ToolResult(
                tool_name="search",
                content=f"results for {q}",
                data={"hits": [{"id": 1}]},
                truncated=True,
            )

        result = await search.execute(q="foo")
        assert result.data == {"hits": [{"id": 1}]}
        assert result.truncated is True


# ---------------------------------------------------------------------------
# Section: Argument validation errors (D-03-5 — first catch site)
# ---------------------------------------------------------------------------


class TestArgumentValidation:
    """Argument errors return ToolResult(is_error=True); body not invoked."""

    @pytest.mark.asyncio
    async def test_missing_required_arg(self) -> None:
        called = False

        @tool(name="strict", description="d")
        async def strict(query: str) -> ToolResult:
            nonlocal called
            called = True
            return ToolResult(tool_name="strict", content=query)

        result = await strict.execute()
        assert result.is_error is True
        assert "Invalid arguments" in result.content
        assert called is False  # body MUST NOT be invoked

    @pytest.mark.asyncio
    async def test_wrong_type(self) -> None:
        @tool(name="strict", description="d")
        async def strict(text: str) -> ToolResult:
            return ToolResult(tool_name="strict", content=text)

        result = await strict.execute(text=42)  # type: ignore[arg-type]
        assert result.is_error is True
        assert "Invalid arguments" in result.content

    @pytest.mark.asyncio
    async def test_extra_kwarg(self) -> None:
        @tool(name="strict", description="d")
        async def strict(text: str) -> ToolResult:
            return ToolResult(tool_name="strict", content=text)

        result = await strict.execute(text="hi", extra="boom")
        assert result.is_error is True
        # Pydantic's "extra fields not permitted" → wording may vary; check shape.
        assert "Invalid arguments" in result.content


# ---------------------------------------------------------------------------
# Section: Function-body exception envelope (D-03-5 — second catch site)
# ---------------------------------------------------------------------------


class TestBodyExceptionEnvelope:
    """Body-raised Exception → ToolResult(is_error=True); never re-raised."""

    @pytest.mark.asyncio
    async def test_value_error_caught(self) -> None:
        @tool(name="boomer", description="d")
        async def boomer(q: str) -> ToolResult:
            raise ValueError("bang")

        result = await boomer.execute(q="x")
        assert result.is_error is True
        assert "ValueError" in result.content
        assert "bang" in result.content

    @pytest.mark.asyncio
    async def test_persona_error_caught(self) -> None:
        # Domain exceptions also get wrapped — the Toolbox's contract is that
        # tools return ToolResult, not raise.
        @tool(name="sandboxy", description="d")
        async def sandboxy(p: str) -> ToolResult:
            raise SandboxViolationError("nope", context={"requested": p})

        result = await sandboxy.execute(p="../etc")
        assert result.is_error is True
        assert "SandboxViolationError" in result.content

    @pytest.mark.asyncio
    async def test_persona_error_base_caught(self) -> None:
        @tool(name="generic", description="d")
        async def generic(q: str) -> ToolResult:
            raise PersonaError("oops", context={"why": "test"})

        result = await generic.execute(q="x")
        assert result.is_error is True
        assert "PersonaError" in result.content

    @pytest.mark.asyncio
    async def test_keyboard_interrupt_propagates(self) -> None:
        @tool(name="ctrlc", description="d")
        async def ctrlc(q: str) -> ToolResult:
            raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            await ctrlc.execute(q="x")

    @pytest.mark.asyncio
    async def test_system_exit_propagates(self) -> None:
        @tool(name="exiter", description="d")
        async def exiter(q: str) -> ToolResult:
            raise SystemExit(0)

        with pytest.raises(SystemExit):
            await exiter.execute(q="x")


# ---------------------------------------------------------------------------
# Section: Decorator misuse
# ---------------------------------------------------------------------------


class TestDecoratorMisuse:
    """The decorator rejects sync functions and other bad inputs."""

    def test_rejects_sync_function(self) -> None:
        with pytest.raises(TypeError, match="async def"):

            @tool(name="bad", description="d")
            def syncy(q: str) -> ToolResult:  # type: ignore[misc]
                return ToolResult(tool_name="bad", content=q)


# ---------------------------------------------------------------------------
# Section: Defensive wrapping of bad return types
# ---------------------------------------------------------------------------


class TestBadReturnType:
    """If the body returns a non-ToolResult, the decorator wraps as error."""

    @pytest.mark.asyncio
    async def test_string_return_wrapped(self) -> None:
        @tool(name="wronger", description="d")
        async def wronger(q: str) -> Any:
            return "just a string"  # type: ignore[return-value]

        result = await wronger.execute(q="x")
        assert isinstance(result, ToolResult)
        assert result.is_error is True
        assert "InvalidToolReturn" in result.content

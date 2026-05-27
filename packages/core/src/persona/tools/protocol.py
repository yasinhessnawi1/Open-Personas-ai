"""Tool Protocol surface for spec 03.

Two Protocols, sibling to spec-01's :class:`persona.schema.tools.Tool`
(D-03-2):

- :class:`ToolDescriptor` — the shared metadata surface (``name``,
  ``description``, ``parameters_schema``). Every tool — spec-01's sync
  :class:`Tool` and spec-03's :class:`AsyncTool` — satisfies this Protocol.
  ``persona.backends.types.tool_spec_from_tool`` accepts anything matching
  ``ToolDescriptor``, so the bridge to provider tool specs works for both.

- :class:`AsyncTool` — extends ``ToolDescriptor`` with an async
  ``execute(**kwargs) -> ToolResult``. Spec 03's built-in tools, the
  ``@tool`` decorator, and MCP adapters all produce ``AsyncTool`` instances.

The ``@tool`` decorator (defined in this module, see :func:`tool`) converts
a typed ``async def`` function into an ``AsyncTool`` implementation.
Argument validation and body exceptions are both caught and re-packaged as
``ToolResult(is_error=True)`` (D-03-5) — tools never raise past the
decorator boundary except for ``BaseException`` subclasses
(``KeyboardInterrupt``, ``SystemExit``).
"""

from __future__ import annotations

import inspect
import typing
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from pydantic import ConfigDict, TypeAdapter, ValidationError, create_model

from persona.logging import get_logger
from persona.schema.tools import ToolCall, ToolResult

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["AsyncTool", "ToolCall", "ToolDescriptor", "ToolResult", "tool"]

_logger = get_logger("tools.decorator")


@runtime_checkable
class ToolDescriptor(Protocol):
    """The minimum metadata surface every tool exposes.

    Spec-01's sync :class:`persona.schema.tools.Tool` Protocol and spec-03's
    :class:`AsyncTool` Protocol are both ``ToolDescriptor`` subtypes. Anything
    that needs only the metadata (provider tool-spec marshalling, toolbox
    registration, allow-list checks) should depend on this Protocol — not on
    a concrete tool type.

    Attributes are typed as read-only properties so implementations are free
    to back them with class attributes, frozen dataclasses, or computed
    properties without changing the surface.
    """

    @property
    def name(self) -> str:
        """Tool name. Matches the persona YAML's ``tools`` allow-list entry."""
        ...

    @property
    def description(self) -> str:
        """One-line description shown to the model when it decides what to call."""
        ...

    @property
    def parameters_schema(self) -> dict[str, Any]:
        """JSON Schema for the tool's keyword arguments."""
        ...


@runtime_checkable
class AsyncTool(ToolDescriptor, Protocol):
    """Async tool — produces a :class:`ToolResult` from keyword arguments.

    Implementations are duck-typed via Protocol structural subtyping. The
    :func:`tool` decorator is the usual way to produce one from a typed
    ``async def`` function; :class:`persona.tools.mcp.adapter.MCPToolAdapter`
    is another producer (wrapping MCP-server tools).

    The contract is total: ``execute`` MUST return a ``ToolResult`` (never
    raise) for any caller-side error category. Domain exceptions raised
    inside the body are caught by the :func:`tool` decorator and converted
    to ``ToolResult(is_error=True, content="<ExceptionType>: <msg>")``.
    """

    async def execute(self, **kwargs: Any) -> ToolResult:  # noqa: ANN401
        """Run the tool. See class docstring for the no-raise contract."""
        ...


# ---------------------------------------------------------------------------
# Section: @tool decorator
# ---------------------------------------------------------------------------


def _argument_model_from_signature(fn: Any) -> type[Any]:  # noqa: ANN401
    """Synthesise a Pydantic model from a function signature.

    Used by the :func:`tool` decorator to both (a) generate ``parameters_schema``
    via :class:`pydantic.TypeAdapter` and (b) validate inbound kwargs at call
    time. One source of truth per D-03-4.

    Resolves PEP 563 string annotations (from ``from __future__ import
    annotations``) via :func:`typing.get_type_hints` against the function's
    module globals — necessary so generic types like ``Literal[...]`` and
    ``int | None`` parse correctly.

    Sets ``extra="forbid"`` so unknown kwargs from the model raise a
    validation error (caught by the decorator and returned as
    ``ToolResult(is_error=True)``).
    """
    sig = inspect.signature(fn)
    # Resolve string annotations (PEP 563) using the function's module globals.
    try:
        resolved_hints = typing.get_type_hints(fn)
    except Exception:  # noqa: BLE001 — best-effort; fall through to raw annotations
        resolved_hints = {}

    fields: dict[str, Any] = {}
    for pname, param in sig.parameters.items():
        if pname == "self":
            continue
        # Prefer the resolved type hint; fall back to raw annotation for edge cases.
        if pname in resolved_hints:
            ann = resolved_hints[pname]
        elif param.annotation is not inspect.Parameter.empty:
            ann = param.annotation
        else:
            ann = Any
        default = param.default if param.default is not inspect.Parameter.empty else ...
        fields[pname] = (ann, default)

    # __config__ forbids extra kwargs so typo'd args from the model fail validation.
    model: type[Any] = create_model(
        f"{fn.__name__}_args",
        __config__=ConfigDict(extra="forbid"),
        **fields,
    )
    return model


def _schema_from_model(model: type[Any]) -> dict[str, Any]:
    """JSON Schema for the argument model. Anthropic + OpenAI accept verbatim."""
    return TypeAdapter(model).json_schema()


class _DecoratedTool:
    """Concrete :class:`AsyncTool` produced by the :func:`tool` decorator.

    Holds the wrapped function, the synthesised Pydantic argument model, and
    the JSON Schema derived from it. ``execute`` validates kwargs against the
    model first (D-03-5 — argument errors return ``ToolResult(is_error=True)``)
    then awaits the body inside an exception-catching envelope.
    """

    def __init__(
        self,
        *,
        name: str,
        description: str,
        fn: Any,  # noqa: ANN401
    ) -> None:
        self._name = name
        self._description = description
        self._fn = fn
        self._argmodel = _argument_model_from_signature(fn)
        self._schema = _schema_from_model(self._argmodel)

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters_schema(self) -> dict[str, Any]:
        # Return a deep-ish copy so callers can mutate without affecting us.
        return dict(self._schema)

    async def execute(self, **kwargs: Any) -> ToolResult:  # noqa: ANN401
        """Validate args, then run the body inside an exception envelope.

        - Argument-validation errors → ``ToolResult(is_error=True,
          content="Invalid arguments: ...")`` (D-03-5). The body is **not** invoked.
        - Body-raised ``Exception`` (NOT ``BaseException``) →
          ``ToolResult(is_error=True, content="<Type>: <msg>")``.
        - ``BaseException`` subclasses (``KeyboardInterrupt``, ``SystemExit``)
          propagate.
        """
        try:
            validated = self._argmodel(**kwargs)
        except ValidationError as ve:
            # Single, terse error string — first error message suffices for
            # the model to retry.
            errs = ve.errors()
            first = errs[0] if errs else {"msg": str(ve)}
            detail = f"{first.get('msg', 'validation failed')}"
            loc = first.get("loc")
            if loc:
                detail = f"{detail} (at {'/'.join(str(x) for x in loc)})"
            _logger.debug("argument validation failed", tool=self._name, detail=detail)
            return ToolResult(
                tool_name=self._name,
                content=f"Invalid arguments: {detail}",
                is_error=True,
            )

        try:
            result = await self._fn(**validated.model_dump())
        except Exception as e:  # noqa: BLE001 — D-03-5 deliberate broad catch
            _logger.debug(
                "tool body raised exception",
                tool=self._name,
                exc_type=type(e).__name__,
            )
            return ToolResult(
                tool_name=self._name,
                content=f"{type(e).__name__}: {e}",
                is_error=True,
            )

        # The wrapped body is contractually expected to return ToolResult; if
        # it returns something else we wrap it defensively.
        if not isinstance(result, ToolResult):
            return ToolResult(
                tool_name=self._name,
                content=f"InvalidToolReturn: {type(result).__name__}: {result!r}",
                is_error=True,
            )
        return result


def tool(
    *,
    name: str,
    description: str,
) -> Callable[[Callable[..., Any]], AsyncTool]:
    """Wrap an ``async def`` function as an :class:`AsyncTool`.

    Args:
        name: Tool name (must be unique within a :class:`Toolbox`).
        description: One-line description the model uses to decide.

    Returns:
        A decorator that wraps an ``async def`` function as an
        :class:`AsyncTool` instance.

    Example:
        >>> @tool(name="echo", description="Echo a string.")
        ... async def echo(text: str) -> ToolResult:
        ...     return ToolResult(tool_name="echo", content=text)
        >>> isinstance(echo, AsyncTool)
        True

    Exception handling per D-03-5: argument-validation errors AND body-raised
    ``Exception`` subclasses are caught and returned as
    ``ToolResult(is_error=True)``. ``BaseException`` (``KeyboardInterrupt``,
    ``SystemExit``) propagates.
    """

    def _decorator(fn: Any) -> _DecoratedTool:  # noqa: ANN401
        if not inspect.iscoroutinefunction(fn):
            msg = (
                f"@tool requires an `async def` function; {fn.__name__} is not a coroutine function"
            )
            raise TypeError(msg)
        return _DecoratedTool(name=name, description=description, fn=fn)

    return _decorator

"""Tests for spec-03 tool / MCP domain exceptions (T02)."""

from __future__ import annotations

import pytest
from persona.errors import (
    MCPConnectionError,
    MCPServerUnavailableError,
    PersonaError,
    SandboxViolationError,
    ToolExecutionError,
    ToolNotAllowedError,
)


class TestMCPConnectionError:
    """:class:`MCPConnectionError` — strict-mode connect failure."""

    def test_is_persona_error(self) -> None:
        assert issubclass(MCPConnectionError, PersonaError)

    def test_accepts_structured_context(self) -> None:
        err = MCPConnectionError(
            "cannot reach server",
            context={"server": "husleietvistutvalget", "url": "https://x.example/mcp"},
        )
        assert "husleietvistutvalget" in str(err)
        assert "url=https://x.example/mcp" in str(err)

    def test_no_context_renders_message_only(self) -> None:
        err = MCPConnectionError("bare")
        assert str(err) == "bare"


class TestMCPServerUnavailableError:
    """:class:`MCPServerUnavailableError` — registered server unreachable."""

    def test_is_persona_error(self) -> None:
        assert issubclass(MCPServerUnavailableError, PersonaError)

    def test_distinct_from_connection_error(self) -> None:
        # D-03-1: flat hierarchy. Neither inherits from the other.
        assert not issubclass(MCPServerUnavailableError, MCPConnectionError)
        assert not issubclass(MCPConnectionError, MCPServerUnavailableError)

    def test_context_rendering(self) -> None:
        err = MCPServerUnavailableError(
            "server down",
            context={"server": "x", "error": "ConnectError"},
        )
        rendered = str(err)
        assert "server=x" in rendered
        assert "error=ConnectError" in rendered


class TestExistingToolErrorsStillPresent:
    """Sanity: spec-01's tool exceptions are still importable from both modules."""

    def test_import_from_persona_errors(self) -> None:
        # Already declared by spec 01 — guard against accidental removal.
        assert issubclass(ToolNotAllowedError, PersonaError)
        assert issubclass(ToolExecutionError, PersonaError)
        assert issubclass(SandboxViolationError, PersonaError)

    def test_import_from_tools_errors(self) -> None:
        from persona.tools import errors as tools_errors

        # Same classes — no duplicate definitions.
        assert tools_errors.MCPConnectionError is MCPConnectionError
        assert tools_errors.MCPServerUnavailableError is MCPServerUnavailableError
        assert tools_errors.ToolNotAllowedError is ToolNotAllowedError
        assert tools_errors.ToolExecutionError is ToolExecutionError
        assert tools_errors.SandboxViolationError is SandboxViolationError


class TestRaisingAndCatching:
    """Callers should be able to catch via PersonaError or the leaf class."""

    def test_catch_as_persona_error(self) -> None:
        with pytest.raises(PersonaError):
            raise MCPConnectionError("test", context={"k": "v"})

    def test_catch_as_leaf(self) -> None:
        with pytest.raises(MCPServerUnavailableError):
            raise MCPServerUnavailableError("test")

    def test_other_leaf_does_not_catch(self) -> None:
        # MCPConnectionError is NOT MCPServerUnavailableError (D-03-1: flat).
        # Verify that a try/except on the wrong leaf does not catch.
        caught_wrong = False
        try:
            raise MCPConnectionError("conn")
        except MCPServerUnavailableError:
            caught_wrong = True  # pragma: no cover — must NOT execute
        except MCPConnectionError:
            pass
        assert caught_wrong is False

"""Tests for the MCPClient lifecycle wrapper (T11)."""

# ruff: noqa: ANN401, ARG001, ARG002, ERA001, SLF001
from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from persona.errors import MCPServerUnavailableError
from persona.tools.audit import MemoryToolAuditLogger
from persona.tools.mcp.client import MCPClient, load_mcp_clients
from persona.tools.protocol import AsyncTool

# Section: SDK shape mocks


def _fake_tools_result(*tool_names: str) -> SimpleNamespace:
    return SimpleNamespace(
        tools=[
            SimpleNamespace(
                name=n,
                description=f"Tool {n}",
                inputSchema={"type": "object", "properties": {"q": {"type": "string"}}},
            )
            for n in tool_names
        ]
    )


def _patch_sdk(
    monkeypatch: pytest.MonkeyPatch,
    *,
    tools: list[str] | None = None,
    transport_raises: Exception | None = None,
    initialize_raises: Exception | None = None,
    list_tools_raises: Exception | None = None,
) -> MagicMock:
    """Patch the streamablehttp_client + ClientSession contexts the MCP client uses.

    Returns a mock object that captures the ClientSession instance for
    assertion (e.g., to verify list_tools was awaited).
    """
    tool_names = tools or ["search"]

    captured: dict[str, Any] = {}

    @asynccontextmanager
    async def fake_transport(_url: str) -> Any:  # noqa: ANN401
        if transport_raises is not None:
            raise transport_raises
        # Return (read, write, get_session_id) tuple.
        yield (MagicMock(name="read"), MagicMock(name="write"), MagicMock(name="get_sid"))

    @asynccontextmanager
    async def fake_session_ctx(_read: Any, _write: Any) -> Any:  # noqa: ANN401
        session = SimpleNamespace(
            initialize=AsyncMock(side_effect=initialize_raises),
            list_tools=AsyncMock(
                side_effect=list_tools_raises,
                return_value=_fake_tools_result(*tool_names),
            ),
            call_tool=AsyncMock(),
        )
        captured["session"] = session
        yield session

    # Patch the import targets inside MCPClient.connect — it does a local
    # import of `from mcp.client.streamable_http import streamablehttp_client`
    # and `from mcp import ClientSession`, so we patch the names that the
    # SDK exposes at those module paths.
    import mcp
    import mcp.client.streamable_http as shttp

    monkeypatch.setattr(shttp, "streamablehttp_client", fake_transport)
    # ClientSession is a class — substitute with a callable that returns the
    # async-context-manager.
    monkeypatch.setattr(mcp, "ClientSession", fake_session_ctx)

    return MagicMock(captured=captured)


# Section: connect happy path


class TestConnectHappy:
    @pytest.mark.asyncio
    async def test_connect_discovers_tools(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_sdk(monkeypatch, tools=["search", "fetch"])
        client = MCPClient(server_name="legal", server_url="https://x/mcp")
        await client.connect()
        assert client.is_connected
        tools = client.get_tools()
        assert len(tools) == 2
        for tool in tools:
            assert isinstance(tool, AsyncTool)
        names = {t.name for t in tools}
        assert names == {"mcp:legal:search", "mcp:legal:fetch"}
        await client.disconnect()

    @pytest.mark.asyncio
    async def test_connect_emits_audit_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_sdk(monkeypatch)
        audit = MemoryToolAuditLogger()
        client = MCPClient(
            server_name="legal",
            server_url="https://x/mcp",
            audit_logger=audit,
            persona_id="bot",
        )
        await client.connect()
        # One audit event: action="connect".
        assert len(audit.events) == 1
        ev = audit.events[0]
        assert ev.action == "connect"
        assert ev.resource == "legal"
        assert ev.tool_name == "mcp:legal"
        assert ev.metadata["transport"] == "streamable_http"
        assert ev.persona_id == "bot"
        await client.disconnect()


# Section: disconnect


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_emits_audit_event(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_sdk(monkeypatch)
        audit = MemoryToolAuditLogger()
        client = MCPClient(server_name="legal", server_url="https://x/mcp", audit_logger=audit)
        await client.connect()
        await client.disconnect(reason="user_close")

        assert not client.is_connected
        assert client.get_tools() == []
        actions = [e.action for e in audit.events]
        assert actions == ["connect", "disconnect"]
        assert audit.events[1].metadata["reason"] == "user_close"

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_sdk(monkeypatch)
        audit = MemoryToolAuditLogger()
        client = MCPClient(server_name="x", server_url="https://x/mcp", audit_logger=audit)
        await client.connect()
        await client.disconnect()
        await client.disconnect()  # second call is a no-op
        actions = [e.action for e in audit.events]
        assert actions == ["connect", "disconnect"]  # NOT duplicated


# Section: strict vs graceful


class TestStrictModeFailure:
    @pytest.mark.asyncio
    async def test_strict_raises_on_transport_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_sdk(monkeypatch, transport_raises=ConnectionError("dns failed"))
        audit = MemoryToolAuditLogger()
        client = MCPClient(server_name="dead", server_url="https://nowhere/mcp", audit_logger=audit)
        with pytest.raises(MCPServerUnavailableError) as exc_info:
            await client.connect(strict=True)
        assert "dead" in str(exc_info.value)
        # Audit emitted server_unavailable.
        assert audit.events[0].action == "server_unavailable"
        assert audit.events[0].is_error is True

    @pytest.mark.asyncio
    async def test_strict_raises_on_initialize_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_sdk(monkeypatch, initialize_raises=RuntimeError("init bad"))
        client = MCPClient(server_name="srv", server_url="https://x/mcp")
        with pytest.raises(MCPServerUnavailableError):
            await client.connect(strict=True)


class TestGracefulModeFailure:
    @pytest.mark.asyncio
    async def test_nonstrict_omits_tools_on_transport_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_sdk(monkeypatch, transport_raises=ConnectionError("dns failed"))
        audit = MemoryToolAuditLogger()
        client = MCPClient(
            server_name="dead",
            server_url="https://nowhere/mcp",
            audit_logger=audit,
        )
        # No exception.
        await client.connect(strict=False)
        # Not connected; no tools.
        assert not client.is_connected
        assert client.get_tools() == []
        # server_unavailable audited.
        assert audit.events[0].action == "server_unavailable"
        assert audit.events[0].is_error is True

    @pytest.mark.asyncio
    async def test_nonstrict_recovers_after_failure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A second connect attempt after a graceful failure can succeed.
        _patch_sdk(monkeypatch, transport_raises=ConnectionError("dns"))
        client = MCPClient(server_name="x", server_url="https://x/mcp")
        await client.connect(strict=False)
        assert not client.is_connected

        # Replace the transport mock so the next connect succeeds.
        _patch_sdk(monkeypatch, tools=["search"])
        await client.connect(strict=False)
        assert client.is_connected
        assert len(client.get_tools()) == 1
        await client.disconnect()


# Section: load_mcp_clients helper


class TestLoadMCPClients:
    @pytest.mark.asyncio
    async def test_loads_multiple_servers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_sdk(monkeypatch, tools=["search"])
        clients = await load_mcp_clients(
            {"a": "https://a/mcp", "b": "https://b/mcp"},
            strict=False,
        )
        assert len(clients) == 2
        for c in clients:
            await c.disconnect()

    @pytest.mark.asyncio
    async def test_graceful_skips_unreachable_in_nonstrict(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_sdk(monkeypatch, transport_raises=ConnectionError("dns"))
        audit = MemoryToolAuditLogger()
        clients = await load_mcp_clients(
            {"a": "https://nowhere/mcp"},
            audit_logger=audit,
            strict=False,
        )
        assert len(clients) == 1
        assert not clients[0].is_connected
        assert clients[0].get_tools() == []
        assert audit.events[0].action == "server_unavailable"


# Section: AsyncTool integration via Toolbox


class TestMCPToolsIntegrateWithToolbox:
    @pytest.mark.asyncio
    async def test_mcp_tools_dispatchable_via_toolbox(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from persona.schema.tools import ToolCall
        from persona.tools.toolbox import Toolbox

        sdk = _patch_sdk(monkeypatch, tools=["search"])
        client = MCPClient(server_name="legal", server_url="https://x/mcp")
        await client.connect()

        # Fake the call_tool result so dispatch returns something useful.
        session = sdk.captured["session"]
        session.call_tool.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="42 results", type="text")],
            isError=False,
            structuredContent=None,
        )

        toolbox = Toolbox(client.get_tools(), allow_list=["mcp:legal:search"])
        result = await toolbox.dispatch(
            ToolCall(name="mcp:legal:search", args={"q": "rent"}, call_id="c1")
        )
        assert result.is_error is False
        assert result.content == "42 results"
        session.call_tool.assert_awaited_once_with("search", arguments={"q": "rent"})

        await client.disconnect()

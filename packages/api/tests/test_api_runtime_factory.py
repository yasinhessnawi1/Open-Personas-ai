"""RuntimeFactory lifecycle + composition (spec 08, T10).

No DB. Verifies the lifecycle contract (aclose → tier_registry.aclose() + MCP
disconnect, D-05-4) and that the factory exposes the per-request loop builders.
The full real-loop end-to-end (scripted backend through the tier registry) is
exercised in the T15 integration suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from persona_api.services.runtime_factory import RuntimeFactory


class _SpyTierRegistry:
    def __init__(self) -> None:
        self.aclose_called = False

    async def aclose(self) -> None:
        self.aclose_called = True


class _SpyMCPClient:
    def __init__(self) -> None:
        self.disconnected = False

    async def disconnect(self) -> None:
        self.disconnected = True


class _FakeEmbedder:
    model_name = "fake"
    dimension = 384

    def encode(self, _texts: object) -> list[list[float]]:  # pragma: no cover - unused here
        return []


def _factory() -> RuntimeFactory:
    return RuntimeFactory(
        rls_engine=object(),  # type: ignore[arg-type] — not used by aclose
        embedder=_FakeEmbedder(),  # type: ignore[arg-type]
        tier_registry=_SpyTierRegistry(),  # type: ignore[arg-type]
        turn_log_writer=object(),  # type: ignore[arg-type]
        audit_root=Path("/tmp/persona-audit-test"),
    )


@pytest.mark.asyncio
async def test_aclose_closes_tier_registry_and_mcp_clients() -> None:
    factory = _factory()
    registry: _SpyTierRegistry = factory._tier_registry  # type: ignore[assignment]
    client = _SpyMCPClient()
    factory._mcp_clients.append(client)  # type: ignore[arg-type]

    await factory.aclose()

    assert registry.aclose_called is True
    assert client.disconnected is True


@pytest.mark.asyncio
async def test_aclose_with_no_mcp_clients_still_closes_registry() -> None:
    factory = _factory()
    registry: _SpyTierRegistry = factory._tier_registry  # type: ignore[assignment]
    await factory.aclose()
    assert registry.aclose_called is True


def test_factory_exposes_loop_builders() -> None:
    factory = _factory()
    assert callable(factory.build_conversation_loop)
    assert callable(factory.build_agentic_loop)

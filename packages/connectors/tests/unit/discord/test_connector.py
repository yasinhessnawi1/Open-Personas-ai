"""DiscordConnector — C1 Connector + C0 MessageDeliverer (Spec C3).

Unit-level (offline): the real client over ``httpx.MockTransport`` proves the send
chain (render → Markdown → REST), a fake store + recording owner-scope prove the
GAP-A deliver bridge, and the DM-ability outcome mapping (un-DMable → failed; cold
origination with no established DM channel → pending) is proven explicitly — never a
crash, never a silent drop.
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import pytest
from persona.delivery import DeliveryOutcome, MessageDeliverer
from persona.schema.origination import OriginatedMessage, PersonaIdentityTag
from persona_connectors.discord.client import DiscordClient
from persona_connectors.discord.connector import DiscordConnector
from persona_connectors.domain.conversation_model import ChannelRef
from persona_connectors.domain.normalise import NormalisedOutbound
from persona_connectors.domain.protocol import Connector
from pydantic import SecretStr

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_TOKEN = "discord-bot-token.secret.zzz"  # noqa: S105 — test literal
_PERSONA = PersonaIdentityTag(persona_id="pa", display_name="Astrid", visual_ref=None)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> DiscordClient:
    return DiscordClient(
        bot_token=SecretStr(_TOKEN),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        api_base_url="https://discord.test/api/v10",
    )


class _FakeStore:
    """A minimal ConversationStateStore stand-in exposing only resolve_channel."""

    def __init__(self, ref: ChannelRef | None) -> None:
        self._ref = ref
        self.seen_conversation_id: str | None = None

    def resolve_channel(self, *, conversation_id: str) -> ChannelRef | None:
        self.seen_conversation_id = conversation_id
        return self._ref


def _scope_recorder(entered: list[str]) -> Callable[[str], object]:
    @contextlib.contextmanager
    def scope(owner_id: str) -> Iterator[None]:
        entered.append(owner_id)
        yield

    return scope


def _connector(
    handler: Callable[[httpx.Request], httpx.Response],
    *,
    ref: ChannelRef | None = None,
    entered: list[str] | None = None,
) -> DiscordConnector:
    return DiscordConnector(
        client=_client(handler),
        conversation_store=_FakeStore(ref),  # type: ignore[arg-type]
        owner_scope=_scope_recorder(entered if entered is not None else []),  # type: ignore[arg-type]
    )


def _originated(conversation_id: str | None) -> OriginatedMessage:
    return OriginatedMessage(
        persona=_PERSONA,
        owner_user_id="user_a",
        content="I've finished the task.",
        conversation_id=conversation_id,
        created_at=datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC),
    )


def _ok(_request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"id": "m1"})


# --- protocol conformance ---


def test_connector_satisfies_both_protocols() -> None:
    connector = _connector(_ok)
    assert isinstance(connector, Connector)
    assert isinstance(connector, MessageDeliverer)
    assert connector.platform == "discord"
    assert connector.capabilities.supports_rich_formatting is True
    assert connector.capabilities.max_body_chars == 2000


# --- send (Connector) ---


@pytest.mark.asyncio
async def test_send_renders_markdown_bold_and_reports_delivered() -> None:
    sent: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v10/channels/dm-5/messages"
        sent["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "m1"})

    result = await _connector(handler).send(
        NormalisedOutbound(persona=_PERSONA, text="hello", conversation_key="dm-5")
    )
    assert result.outcome == DeliveryOutcome.DELIVERED
    assert result.channel == "discord"
    assert sent["body"] == {"content": "**Astrid**\nhello"}


@pytest.mark.asyncio
async def test_send_rate_limited_reports_pending() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited", "retry_after": 2.0})

    result = await _connector(handler).send(
        NormalisedOutbound(persona=_PERSONA, text="x", conversation_key="dm-5")
    )
    assert result.outcome == DeliveryOutcome.PENDING
    assert _TOKEN not in (result.detail or "")


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [50007, 50278])
async def test_send_cannot_dm_reports_failed_with_warm_detail(code: int) -> None:
    """The DM-ability gate → FAILED with an actionable detail (never a crash/silent drop)."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"code": code, "message": "Cannot send"})

    result = await _connector(handler).send(
        NormalisedOutbound(persona=_PERSONA, text="x", conversation_key="dm-5")
    )
    assert result.outcome == DeliveryOutcome.FAILED
    assert "message me first" in (result.detail or "")
    assert _TOKEN not in (result.detail or "")


@pytest.mark.asyncio
async def test_send_generic_rejection_reports_failed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 50035, "message": "Invalid Form Body"})

    result = await _connector(handler).send(
        NormalisedOutbound(persona=_PERSONA, text="x", conversation_key="dm-5")
    )
    assert result.outcome == DeliveryOutcome.FAILED


# --- deliver (MessageDeliverer / GAP-A bridge) ---


@pytest.mark.asyncio
async def test_deliver_resolves_channel_then_sends() -> None:
    sent: dict[str, object] = {}
    entered: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v10/channels/dm-9/messages"
        sent["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "m1"})

    connector = _connector(
        handler, ref=ChannelRef(platform="discord", channel_key="dm-9"), entered=entered
    )
    result = await connector.deliver(_originated("conv_abc"))

    assert result.outcome == DeliveryOutcome.DELIVERED
    assert entered == ["user_a"]  # owner scope entered with the originated owner
    assert sent["body"] == {"content": "**Astrid**\nI've finished the task."}


@pytest.mark.asyncio
async def test_deliver_no_conversation_is_pending() -> None:
    result = await _connector(_ok).deliver(_originated(None))
    assert result.outcome == DeliveryOutcome.PENDING


@pytest.mark.asyncio
async def test_deliver_no_established_dm_channel_is_pending() -> None:
    """Cold origination with no connector channel → pending (the conditional-DM gate)."""
    result = await _connector(_ok, ref=None).deliver(_originated("conv_web_only"))
    assert result.outcome == DeliveryOutcome.PENDING
    assert result.detail == "no established Discord DM channel"


@pytest.mark.asyncio
async def test_deliver_other_platform_channel_is_pending() -> None:
    result = await _connector(_ok, ref=ChannelRef(platform="telegram", channel_key="555")).deliver(
        _originated("conv_tg")
    )
    assert result.outcome == DeliveryOutcome.PENDING

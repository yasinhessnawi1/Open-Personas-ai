"""SlackConnector — C1 Connector + C0 MessageDeliverer (Spec C3).

Unit-level (offline): the real client over ``httpx.MockTransport`` proves the send chain
(render → mrkdwn → Web API), a fake store + recording owner-scope prove the GAP-A deliver
bridge. Slack DMs are unconditional → there is NO cannot-deliver gate (unlike Discord):
rate-limit → pending, other rejection → failed; no resolvable channel → pending.
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
from persona_connectors.domain.conversation_model import ChannelRef
from persona_connectors.domain.normalise import NormalisedOutbound
from persona_connectors.domain.protocol import Connector
from persona_connectors.slack.client import SlackClient
from persona_connectors.slack.connector import SlackConnector
from pydantic import SecretStr

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

_TOKEN = "xoxb-slack-token.secret"  # noqa: S105 — test literal
_PERSONA = PersonaIdentityTag(persona_id="pa", display_name="Astrid", visual_ref=None)


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> SlackClient:
    return SlackClient(
        bot_token=SecretStr(_TOKEN),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        api_base_url="https://slack.test/api",
    )


class _FakeStore:
    def __init__(self, ref: ChannelRef | None) -> None:
        self._ref = ref

    def resolve_channel(self, *, conversation_id: str) -> ChannelRef | None:  # noqa: ARG002
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
) -> SlackConnector:
    return SlackConnector(
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
    return httpx.Response(200, json={"ok": True, "ts": "1.1"})


def test_connector_satisfies_both_protocols() -> None:
    connector = _connector(_ok)
    assert isinstance(connector, Connector)
    assert isinstance(connector, MessageDeliverer)
    assert connector.platform == "slack"
    assert connector.capabilities.supports_typing_indicator is False  # no bot typing in DMs


@pytest.mark.asyncio
async def test_send_renders_mrkdwn_bold_and_reports_delivered() -> None:
    sent: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat.postMessage"
        sent["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "ts": "1.1"})

    result = await _connector(handler).send(
        NormalisedOutbound(persona=_PERSONA, text="hello", conversation_key="D5")
    )
    assert result.outcome == DeliveryOutcome.DELIVERED
    assert result.channel == "slack"
    assert sent["body"] == {"channel": "D5", "text": "*Astrid*\nhello"}


@pytest.mark.asyncio
async def test_send_rate_limited_reports_pending() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "2"})

    result = await _connector(handler).send(
        NormalisedOutbound(persona=_PERSONA, text="x", conversation_key="D5")
    )
    assert result.outcome == DeliveryOutcome.PENDING
    assert _TOKEN not in (result.detail or "")


@pytest.mark.asyncio
async def test_send_ok_false_reports_failed() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "channel_not_found"})

    result = await _connector(handler).send(
        NormalisedOutbound(persona=_PERSONA, text="x", conversation_key="Dx")
    )
    assert result.outcome == DeliveryOutcome.FAILED
    assert _TOKEN not in (result.detail or "")


@pytest.mark.asyncio
async def test_deliver_resolves_channel_then_sends() -> None:
    sent: dict[str, object] = {}
    entered: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "ts": "1.1"})

    connector = _connector(
        handler, ref=ChannelRef(platform="slack", channel_key="D9"), entered=entered
    )
    result = await connector.deliver(_originated("conv_abc"))
    assert result.outcome == DeliveryOutcome.DELIVERED
    assert entered == ["user_a"]
    assert sent["body"] == {"channel": "D9", "text": "*Astrid*\nI've finished the task."}


@pytest.mark.asyncio
async def test_deliver_no_channel_is_pending() -> None:
    result = await _connector(_ok, ref=None).deliver(_originated("conv_web_only"))
    assert result.outcome == DeliveryOutcome.PENDING
    assert result.detail == "no connector channel for conversation"


@pytest.mark.asyncio
async def test_deliver_other_platform_channel_is_pending() -> None:
    result = await _connector(_ok, ref=ChannelRef(platform="discord", channel_key="dm-1")).deliver(
        _originated("conv_d")
    )
    assert result.outcome == DeliveryOutcome.PENDING

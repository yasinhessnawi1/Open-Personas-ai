"""Slack InboundFlow (Spec C3) — the surface I/O over the shared flow (pure delegation).

Proves the Slack wiring: classify → (ignore | non-text decline | delegate to SharedInboundFlow);
the transport sends via the client/connector; typing is a no-op (Slack DMs have none);
im-only + loop-prevention drop channel/own messages before any turn.
"""
# ruff: noqa: ARG002 — the fakes mirror real protocol signatures; unused params are intentional.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from persona.delivery import DeliveryOutcome, DeliveryResult
from persona_connectors.domain.conversation_model import ForegroundRef, ForegroundResult
from persona_connectors.domain.resolution import ResolvedIdentity, UnlinkedIdentity
from persona_connectors.domain.system_replies import NEW_CONVERSATION_MESSAGE
from persona_connectors.slack.flow import InboundFlow

if TYPE_CHECKING:
    from persona_connectors.domain.flow import TurnRequest

_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
_CHAN = "D5"
_BOT = "U_BOT"
_NAMES = {"astrid": ["Astrid"], "kai": ["Kai"]}


class _FakeClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []

    async def chat_post_message(self, *, channel: str, text: str) -> dict[str, object]:
        self.messages.append((channel, text))
        return {"ok": True}


class _FakeConnector:
    def __init__(self) -> None:
        self.sent: list[object] = []

    async def send(self, outbound: object) -> DeliveryResult:
        self.sent.append(outbound)
        return DeliveryResult(outcome=DeliveryOutcome.DELIVERED, channel="slack")


class _FakeResolver:
    def __init__(self, result: object) -> None:
        self._result = result

    def resolve(self, inbound: object) -> object:
        return self._result


class _FakeStore:
    def __init__(self, *, active: ForegroundRef | None = None) -> None:
        self.active = active
        self.foregrounded: list[str] = []
        self.applied_new: list[str] = []

    def current_foreground(
        self, *, owner_id: str, platform: str, channel_key: str
    ) -> ForegroundRef | None:
        return self.active

    def foreground(
        self, *, owner_id: str, platform: str, channel_key: str, persona_id: str
    ) -> ForegroundResult:
        self.foregrounded.append(persona_id)
        return ForegroundResult(conversation_id=f"conv_{persona_id}", resumed=False)

    def apply_new(self, *, owner_id: str, platform: str, channel_key: str) -> str | None:
        self.applied_new.append(channel_key)
        return "conv_new"


class _TurnRunner:
    def __init__(self) -> None:
        self.requests: list[TurnRequest] = []

    async def __call__(self, request: TurnRequest) -> str:
        await asyncio.sleep(0)
        self.requests.append(request)
        return "Hello from the persona"


def _flow(
    *,
    resolver: object = None,
    store: _FakeStore | None = None,
    names: dict[str, list[str]] | None = None,
) -> tuple[InboundFlow, _FakeClient, _FakeConnector, _FakeStore, _TurnRunner]:
    client = _FakeClient()
    connector = _FakeConnector()
    store = store or _FakeStore()
    turn = _TurnRunner()
    resolver = resolver or _FakeResolver(ResolvedIdentity(owner_id="user_a"))
    resolved_names = _NAMES if names is None else names
    flow = InboundFlow(
        resolver=resolver,  # type: ignore[arg-type]
        conversation_store=store,  # type: ignore[arg-type]
        connector=connector,  # type: ignore[arg-type]
        client=client,  # type: ignore[arg-type]
        list_persona_names=lambda _owner: resolved_names,
        run_turn=turn,
        now=lambda: _NOW,
        bot_user_id=_BOT,
    )
    return flow, client, connector, store, turn


def _event(text: str, *, user: str = "U7", channel_type: str = "im") -> dict[str, object]:
    return {
        "type": "message",
        "channel_type": channel_type,
        "channel": _CHAN,
        "user": user,
        "text": text,
        "ts": "1700000000.000100",
    }


@pytest.mark.asyncio
async def test_channel_message_is_ignored() -> None:
    flow, client, connector, _store, turn = _flow()
    await flow.handle(_event("Kai, hi", channel_type="channel"))
    assert client.messages == []
    assert connector.sent == []
    assert turn.requests == []


@pytest.mark.asyncio
async def test_own_message_is_ignored() -> None:
    flow, client, _connector, _store, turn = _flow()
    await flow.handle(_event("Kai, hi", user=_BOT))
    assert client.messages == []
    assert turn.requests == []


@pytest.mark.asyncio
async def test_file_upload_declines() -> None:
    flow, client, _connector, _store, turn = _flow()
    event = {
        "type": "message",
        "channel_type": "im",
        "channel": _CHAN,
        "user": "U7",
        "ts": "1700000000.000100",
        "files": [{"id": "F1"}],
    }
    await flow.handle(event)
    assert len(client.messages) == 1
    assert "text" in client.messages[0][1].lower()
    assert turn.requests == []


@pytest.mark.asyncio
async def test_unlinked_identity_gets_link_instruction_zero_access() -> None:
    flow, client, connector, _store, turn = _flow(
        resolver=_FakeResolver(UnlinkedIdentity(instruction="link this Slack account"))
    )
    await flow.handle(_event("Kai, hello"))
    assert client.messages == [(_CHAN, "link this Slack account")]
    assert connector.sent == []
    assert turn.requests == []


@pytest.mark.asyncio
async def test_new_resets_and_confirms() -> None:
    flow, client, _connector, store, _turn = _flow()
    await flow.handle(_event("/new"))
    assert store.applied_new == [_CHAN]
    assert client.messages == [(_CHAN, NEW_CONVERSATION_MESSAGE)]


@pytest.mark.asyncio
async def test_addressed_persona_is_driven_no_typing_call() -> None:
    """The persona is driven + reply sent; Slack makes NO typing call (no-op transport)."""
    flow, _client, connector, store, turn = _flow()
    await flow.handle(_event("Kai, how are you?"))
    assert store.foregrounded == ["kai"]
    assert turn.requests[0].persona_id == "kai"
    assert len(connector.sent) == 1
    assert connector.sent[0].persona.display_name == "Kai"  # type: ignore[attr-defined]
    assert connector.sent[0].conversation_key == _CHAN  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_no_name_continues_active_persona() -> None:
    store = _FakeStore(active=ForegroundRef(persona_id="astrid", conversation_id="conv_astrid"))
    flow, _client, connector, store, turn = _flow(store=store)
    await flow.handle(_event("how are you?"))
    assert store.foregrounded == ["astrid"]
    assert connector.sent[0].persona.display_name == "Astrid"  # type: ignore[attr-defined]

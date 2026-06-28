"""Discord InboundFlow (Spec C3) — the surface I/O over the shared flow (pure delegation).

Proves the Discord wiring: classify → (ignore | non-text decline | delegate to
SharedInboundFlow); the transport sends via the client/connector; the no-streaming typing
fires; DM-only + loop-prevention drop guild/own messages before any turn. The routing
DECISION is the shared flow's (tested in test_flow at the unit root); here the resolver is
faked (the binding-shape symmetry that makes a Discord identity resolve is proven in
test_linking) so this is the I/O-wiring proof, mirroring the Telegram flow test.
"""
# ruff: noqa: ARG002 — the fakes mirror real protocol signatures; unused params are intentional.

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from persona.delivery import DeliveryOutcome, DeliveryResult
from persona_connectors.discord.flow import InboundFlow
from persona_connectors.domain.conversation_model import ForegroundRef, ForegroundResult
from persona_connectors.domain.resolution import ResolvedIdentity, UnlinkedIdentity
from persona_connectors.domain.system_replies import NEW_CONVERSATION_MESSAGE

if TYPE_CHECKING:
    from persona_connectors.domain.flow import TurnRequest

_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
_CHAN = "dm-5"
_BOT = "bot1"
_NAMES = {"astrid": ["Astrid"], "kai": ["Kai"]}


class _FakeClient:
    def __init__(self) -> None:
        self.messages: list[tuple[str, str]] = []
        self.typing: list[str] = []

    async def send_message(self, *, channel_id: str, content: str) -> dict[str, object]:
        self.messages.append((channel_id, content))
        return {"id": "m1"}

    async def trigger_typing(self, *, channel_id: str) -> None:
        self.typing.append(channel_id)


class _FakeConnector:
    def __init__(self) -> None:
        self.sent: list[object] = []

    async def send(self, outbound: object) -> DeliveryResult:
        self.sent.append(outbound)
        return DeliveryResult(outcome=DeliveryOutcome.DELIVERED, channel="discord")


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
        await asyncio.sleep(0)  # yield so the typing refresh fires once
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


def _event(text: str, *, sender: str = "user-7", channel: str = _CHAN) -> dict[str, object]:
    return {
        "id": "m9",
        "channel_id": channel,
        "author": {"id": sender, "username": "Yasin"},
        "content": text,
        "timestamp": "2026-06-27T12:00:00+00:00",
    }


# --- DM-only + loop prevention (classify drops these before any turn) ---


@pytest.mark.asyncio
async def test_guild_message_is_ignored() -> None:
    flow, client, connector, _store, turn = _flow()
    event = _event("Kai, hi")
    event["guild_id"] = "guild-1"
    await flow.handle(event)
    assert client.messages == []
    assert connector.sent == []
    assert turn.requests == []


@pytest.mark.asyncio
async def test_own_message_is_ignored() -> None:
    flow, client, connector, _store, turn = _flow()
    await flow.handle(_event("Kai, hi", sender=_BOT))
    assert client.messages == []
    assert turn.requests == []


@pytest.mark.asyncio
async def test_non_text_voice_declines() -> None:
    flow, client, _connector, _store, turn = _flow()
    event = {
        "id": "m9",
        "channel_id": _CHAN,
        "author": {"id": "user-7"},
        "content": "",
        "flags": 1 << 13,
    }
    await flow.handle(event)
    assert len(client.messages) == 1
    assert "voice" in client.messages[0][1].lower()
    assert turn.requests == []


# --- ownership + commands + routing (delegated to the shared flow) ---


@pytest.mark.asyncio
async def test_unlinked_identity_gets_link_instruction_zero_access() -> None:
    flow, client, connector, _store, turn = _flow(
        resolver=_FakeResolver(UnlinkedIdentity(instruction="link this Discord account"))
    )
    await flow.handle(_event("Kai, hello"))
    assert client.messages == [(_CHAN, "link this Discord account")]
    assert connector.sent == []
    assert turn.requests == []


@pytest.mark.asyncio
async def test_new_resets_and_confirms() -> None:
    flow, client, _connector, store, _turn = _flow()
    await flow.handle(_event("/new"))
    assert store.applied_new == [_CHAN]
    assert client.messages == [(_CHAN, NEW_CONVERSATION_MESSAGE)]


@pytest.mark.asyncio
async def test_addressed_persona_is_driven_with_typing() -> None:
    flow, client, connector, store, turn = _flow()
    await flow.handle(_event("Kai, how are you?"))

    assert store.foregrounded == ["kai"]
    assert turn.requests[0].persona_id == "kai"
    assert turn.requests[0].text == "Kai, how are you?"
    assert len(connector.sent) == 1
    assert connector.sent[0].persona.display_name == "Kai"  # type: ignore[attr-defined]
    assert connector.sent[0].conversation_key == _CHAN  # type: ignore[attr-defined]
    assert client.typing == [_CHAN]  # the no-streaming typing window fired


@pytest.mark.asyncio
async def test_no_name_continues_active_persona() -> None:
    store = _FakeStore(active=ForegroundRef(persona_id="astrid", conversation_id="conv_astrid"))
    flow, _client, connector, store, turn = _flow(store=store)
    await flow.handle(_event("how are you?"))
    assert store.foregrounded == ["astrid"]
    assert connector.sent[0].persona.display_name == "Astrid"  # type: ignore[attr-defined]

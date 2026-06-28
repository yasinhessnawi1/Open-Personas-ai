"""The assembled Discord flow, end-to-end on real PG (Spec C3 — the automated leg).

The agent-runnable half of the live leg: a real Discord ``MESSAGE_CREATE`` drives the WHOLE
assembled flow against **real Postgres** (identity resolution on the dispatch engine, persona
listing + foreground under RLS) and a **faithful REST stub** (httpx MockTransport), with only
``run_turn`` stubbed. Proves inbound → resolve → route → foreground → (turn) → render → send,
AND that ownership holds: an unlinked sender gets a link-instruction and zero access.

The real-Discord round-trip (real bot token via the gateway) is the user-run operator pass
(close-out runbook); this is the CI-automatable proof.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import httpx
import pytest
from persona_api.middleware.rls_context import current_user_id
from persona_connectors.composition import build_persona_name_lister
from persona_connectors.discord.client import DiscordClient
from persona_connectors.discord.connector import DiscordConnector
from persona_connectors.discord.flow import InboundFlow
from persona_connectors.domain.linking import LinkingService
from persona_connectors.domain.resolution import InboundIdentityResolver
from persona_connectors.infra import PostgresConversationStateStore, PostgresLinkStore
from pydantic import SecretStr
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Iterator

    from persona_connectors.domain.flow import TurnRequest
    from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

_ASTRID_YAML = "identity:\n  name: Astrid\n  role: companion\n  background: helpful"
_BOT = "bot1"


@contextlib.contextmanager
def _owner_scope(owner_id: str) -> Iterator[None]:
    token = current_user_id.set(owner_id)
    try:
        yield
    finally:
        current_user_id.reset(token)


def _recording_client(records: list[tuple[str, dict[str, object]]]) -> DiscordClient:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        records.append((path, body))
        if path.endswith("/typing"):
            return httpx.Response(204)
        return httpx.Response(200, json={"id": "m1"})

    return DiscordClient(
        bot_token=SecretStr("bot-token"),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        api_base_url="https://discord.test/api/v10",
    )


def _assemble_flow(
    *,
    app_engine: Engine,
    dispatch_engine: Engine,
    records: list[tuple[str, dict[str, object]]],
    reply: str = "Hi, I'm here.",
) -> InboundFlow:
    client = _recording_client(records)
    link_store = PostgresLinkStore(rls_engine=app_engine, dispatch_engine=dispatch_engine)
    linking = LinkingService(link_store)
    conversation_store = PostgresConversationStateStore(
        rls_engine=app_engine, dispatch_engine=dispatch_engine
    )
    connector = DiscordConnector(
        client=client, conversation_store=conversation_store, owner_scope=_owner_scope
    )

    async def run_turn(_request: TurnRequest) -> str:
        await asyncio.sleep(0)  # yield so the typing task fires (a real turn awaits)
        return reply

    return InboundFlow(
        resolver=InboundIdentityResolver(linking),
        conversation_store=conversation_store,
        connector=connector,
        client=client,
        list_persona_names=build_persona_name_lister(
            rls_engine=app_engine, owner_scope=_owner_scope
        ),
        run_turn=run_turn,
        now=lambda: datetime.now(UTC),
        bot_user_id=_BOT,
    )


def _seed_astrid_and_link(engine: Engine, *, sender_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("UPDATE personas SET yaml = :y WHERE id = 'pa'"), {"y": _ASTRID_YAML})
        conn.execute(
            text(
                "INSERT INTO connector_identities "
                "(platform, platform_identity, owner_id, status, linked_at) "
                "VALUES ('discord', :sid, 'user_a', 'active', now())"
            ),
            {"sid": sender_id},
        )


def _event(text_body: str, *, sender_id: str, channel_id: str) -> dict[str, object]:
    return {
        "id": "9",
        "channel_id": channel_id,
        "author": {"id": sender_id, "username": "yasin"},
        "content": text_body,
        "timestamp": "2026-06-27T12:00:00+00:00",
    }


@pytest.mark.asyncio
async def test_linked_inbound_drives_a_persona_reply_to_discord(
    app_engine: Engine, migrated_engine: Engine
) -> None:
    """A linked sender addressing Astrid → the persona reply is sent to their DM channel."""
    _seed_astrid_and_link(migrated_engine, sender_id="999")
    records: list[tuple[str, dict[str, object]]] = []
    flow = _assemble_flow(app_engine=app_engine, dispatch_engine=migrated_engine, records=records)

    await flow.handle(_event("Astrid, hello", sender_id="999", channel_id="dm-42"))

    sends = [body for path, body in records if path.endswith("/dm-42/messages")]
    assert len(sends) == 1
    assert "**Astrid**" in str(sends[0]["content"])  # the Markdown name tag rendered
    assert "Hi, I'm here." in str(sends[0]["content"])
    # The typing indicator fired while the turn ran (D-C2-4 carried forward).
    assert any(path.endswith("/typing") for path, _ in records)

    with _owner_scope("user_a"), app_engine.begin() as conn:
        active = conn.execute(
            text(
                "SELECT active_persona_id FROM connector_channels "
                "WHERE owner_id='user_a' AND platform='discord' AND channel_key='dm-42'"
            )
        ).scalar()
    assert active == "pa"


@pytest.mark.asyncio
async def test_unlinked_inbound_gets_link_instruction_zero_access(
    app_engine: Engine, migrated_engine: Engine
) -> None:
    """Ownership over the platform: an unlinked sender reaches NO persona (criterion 9)."""
    records: list[tuple[str, dict[str, object]]] = []
    flow = _assemble_flow(app_engine=app_engine, dispatch_engine=migrated_engine, records=records)

    await flow.handle(_event("Astrid, hello", sender_id="888", channel_id="dm-66"))

    sends = [body for path, body in records if path.endswith("/messages")]
    assert len(sends) == 1
    assert "link" in str(sends[0]["content"]).lower()  # the link-instruction
    assert "**Astrid**" not in str(sends[0]["content"])  # no persona was reached

    with migrated_engine.begin() as conn:
        channels = conn.execute(
            text("SELECT count(*) FROM connector_channels WHERE channel_key='dm-66'")
        ).scalar()
    assert channels == 0

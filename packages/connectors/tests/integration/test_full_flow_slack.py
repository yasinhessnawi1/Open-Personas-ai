"""The assembled Slack flow, end-to-end on real PG (Spec C3 — the automated leg).

A real Slack ``message.im`` event drives the WHOLE assembled flow against **real Postgres**
and a **faithful Web-API stub** (httpx MockTransport), with only ``run_turn`` stubbed. Proves
inbound → resolve → route → foreground → (turn) → render → send, AND that ownership holds: an
unlinked sender gets a link-instruction and zero access.

The real-Slack round-trip (real workspace via socket mode) is the user-run operator pass
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
from persona_connectors.domain.linking import LinkingService
from persona_connectors.domain.resolution import InboundIdentityResolver
from persona_connectors.infra import PostgresConversationStateStore, PostgresLinkStore
from persona_connectors.slack.client import SlackClient
from persona_connectors.slack.connector import SlackConnector
from persona_connectors.slack.flow import InboundFlow
from pydantic import SecretStr
from sqlalchemy import text

if TYPE_CHECKING:
    from collections.abc import Iterator

    from persona_connectors.domain.flow import TurnRequest
    from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

_ASTRID_YAML = "identity:\n  name: Astrid\n  role: companion\n  background: helpful"
_BOT = "U_BOT"


@contextlib.contextmanager
def _owner_scope(owner_id: str) -> Iterator[None]:
    token = current_user_id.set(owner_id)
    try:
        yield
    finally:
        current_user_id.reset(token)


def _recording_client(records: list[tuple[str, dict[str, object]]]) -> SlackClient:
    def handler(request: httpx.Request) -> httpx.Response:
        records.append((request.url.path, json.loads(request.content) if request.content else {}))
        return httpx.Response(200, json={"ok": True, "ts": "1.1"})

    return SlackClient(
        bot_token=SecretStr("xoxb-token"),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        api_base_url="https://slack.test/api",
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
    connector = SlackConnector(
        client=client, conversation_store=conversation_store, owner_scope=_owner_scope
    )

    async def run_turn(_request: TurnRequest) -> str:
        await asyncio.sleep(0)
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
                "VALUES ('slack', :sid, 'user_a', 'active', now())"
            ),
            {"sid": sender_id},
        )


def _event(text_body: str, *, sender_id: str, channel: str) -> dict[str, object]:
    return {
        "type": "message",
        "channel_type": "im",
        "channel": channel,
        "user": sender_id,
        "text": text_body,
        "ts": "1700000000.000100",
    }


@pytest.mark.asyncio
async def test_linked_inbound_drives_a_persona_reply_to_slack(
    app_engine: Engine, migrated_engine: Engine
) -> None:
    """A linked sender addressing Astrid → the persona reply is posted to their im channel."""
    _seed_astrid_and_link(migrated_engine, sender_id="U7")
    records: list[tuple[str, dict[str, object]]] = []
    flow = _assemble_flow(app_engine=app_engine, dispatch_engine=migrated_engine, records=records)

    await flow.handle(_event("Astrid, hello", sender_id="U7", channel="D5"))

    posts = [body for path, body in records if path.endswith("/chat.postMessage")]
    assert len(posts) == 1
    assert posts[0]["channel"] == "D5"
    assert "*Astrid*" in str(posts[0]["text"])  # the mrkdwn (single-asterisk) name tag
    assert "Hi, I'm here." in str(posts[0]["text"])

    with _owner_scope("user_a"), app_engine.begin() as conn:
        active = conn.execute(
            text(
                "SELECT active_persona_id FROM connector_channels "
                "WHERE owner_id='user_a' AND platform='slack' AND channel_key='D5'"
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

    await flow.handle(_event("Astrid, hello", sender_id="U9", channel="D6"))

    posts = [body for path, body in records if path.endswith("/chat.postMessage")]
    assert len(posts) == 1
    assert "link" in str(posts[0]["text"]).lower()
    assert "*Astrid*" not in str(posts[0]["text"])  # no persona was reached

    with migrated_engine.begin() as conn:
        channels = conn.execute(
            text("SELECT count(*) FROM connector_channels WHERE channel_key='D6'")
        ).scalar()
    assert channels == 0

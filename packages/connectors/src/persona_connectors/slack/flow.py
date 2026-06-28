"""The Slack inbound flow (Spec C3) — the Slack surface over the shared flow.

A Slack ``message.im`` event runs through: classify → (ignore | non-text decline | delegate
to the shared flow). The platform-agnostic sequence (resolve → ``/new`` → route → drive the
turn → send) is C1's :class:`~persona_connectors.domain.flow.SharedInboundFlow`
(D-C3-X-flow-skeleton), shared with Telegram + Discord. This module supplies only the
**Slack surface**: the inbound classification (``im``-only — D-C3-5), the non-text decline,
and the platform I/O behind :class:`~persona_connectors.domain.flow.FlowTransport`.

**No auth carrier in the inbound path** (like Discord): Slack linking is OAuth, completed
out-of-band on the callback route (``slack/app.py``) — the flow only READS the binding via
the shared ``resolver.resolve`` (the binding-symmetry proven in the OAuth task). **Typing is
a no-op:** Slack has no bot typing indicator for plain DMs (the no-streaming reply just sends
whole — criterion 7's "where the platform supports one").

**api-free**: the api-coupled callables (``run_turn`` / ``list_persona_names``) are injected,
owner-scoped by the composition root. Ownership holds exactly as on the web (the shared C1
resolution gate): an unlinked identity gets a link-instruction and ZERO access.
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

from persona_connectors.domain.flow import SharedInboundFlow
from persona_connectors.slack.inbound import InboundIgnore, InboundNonText, classify_event
from persona_connectors.slack.non_text import decline_message

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
    from datetime import datetime

    from persona_connectors.domain.conversation_model import ConversationStateStore
    from persona_connectors.domain.flow import TurnRequest
    from persona_connectors.domain.normalise import NormalisedOutbound
    from persona_connectors.domain.resolution import InboundIdentityResolver
    from persona_connectors.slack.client import SlackClient
    from persona_connectors.slack.connector import SlackConnector

__all__ = ["InboundFlow"]


@contextlib.asynccontextmanager
async def _no_typing(_conversation_key: str) -> AsyncIterator[None]:
    """A no-op typing window — Slack plain DMs have no bot typing indicator (D-C3-6)."""
    yield


class _SlackFlowTransport:
    """Slack's :class:`FlowTransport` — pure I/O, no auth; typing is a no-op."""

    def __init__(self, *, client: SlackClient, connector: SlackConnector) -> None:
        self._client = client
        self._connector = connector

    async def send_system(self, *, conversation_key: str, text: str) -> None:
        await self._client.chat_post_message(channel=conversation_key, text=text)

    async def send_persona(self, outbound: NormalisedOutbound) -> None:
        await self._connector.send(outbound)

    def typing(self, conversation_key: str) -> contextlib.AbstractAsyncContextManager[None]:
        return _no_typing(conversation_key)


class InboundFlow:
    """Orchestrates one inbound Slack event — the Slack surface over the shared flow.

    All dependencies are injected (DI; no globals). ``bot_user_id`` (resolved at startup via
    ``SlackClient.auth_test``) lets the classifier ignore the app's own echoes (loop
    prevention). The api-coupled callables are owner-scoped by the composition root.
    """

    def __init__(
        self,
        *,
        resolver: InboundIdentityResolver,
        conversation_store: ConversationStateStore,
        connector: SlackConnector,
        client: SlackClient,
        list_persona_names: Callable[[str], Mapping[str, Sequence[str]]],
        run_turn: Callable[[TurnRequest], Awaitable[str]],
        now: Callable[[], datetime],
        bot_user_id: str,
    ) -> None:
        self._client = client
        self._now = now
        self._bot_user_id = bot_user_id
        self._transport = _SlackFlowTransport(client=client, connector=connector)
        self._shared = SharedInboundFlow(
            resolver=resolver,
            conversation_store=conversation_store,
            list_persona_names=list_persona_names,
            run_turn=run_turn,
        )

    async def handle(self, event: dict[str, object]) -> None:
        """Handle one Slack ``message`` event (the transport's ``on_event``)."""
        outcome = classify_event(event, bot_user_id=self._bot_user_id, now=self._now())
        if isinstance(outcome, InboundIgnore):
            return
        if isinstance(outcome, InboundNonText):
            await self._client.chat_post_message(
                channel=outcome.conversation_key, text=decline_message(outcome.kind)
            )
            return
        await self._shared.handle_text(outcome.inbound, transport=self._transport)

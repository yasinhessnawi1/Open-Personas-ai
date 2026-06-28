"""The Discord inbound flow (Spec C3) — the Discord surface over the shared flow.

A gateway ``MESSAGE_CREATE`` event runs through: classify → (ignore | non-text decline
| delegate to the shared flow). The platform-agnostic sequence (resolve → ``/new`` →
route → drive the turn → send) is C1's
:class:`~persona_connectors.domain.flow.SharedInboundFlow` (D-C3-X-flow-skeleton), shared
with Telegram + Slack. This module supplies only the **Discord surface**: the inbound
classification (DM-only — D-C3-5), the non-text decline, and the platform I/O behind
:class:`~persona_connectors.domain.flow.FlowTransport` (the no-streaming typing loop, the
system/persona sends).

**No auth carrier in the inbound path.** Unlike Telegram's inline ``/start`` redeem,
Discord's account-linking is **OAuth, completed out-of-band on the callback route**
(``discord/app.py``) — so the binding WRITE never touches this flow; it only ever READS
the binding (via the shared ``resolver.resolve``). That read resolves a Discord-linked
identity identically to a Telegram one (the binding-shape symmetry proven in the OAuth
task), so the shared flow Just Works on Discord.

**api-free**: the api-coupled bits (running the turn, listing personas) are injected
callables; this module imports no ``persona_api``. Ownership holds exactly as on the web
(the shared C1 resolution gate): an unlinked identity gets a link-instruction and ZERO
access; a resolved owner only ever touches their own personas.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from persona_connectors.discord.inbound import InboundIgnore, InboundNonText, classify_message
from persona_connectors.discord.non_text import decline_message
from persona_connectors.domain.flow import SharedInboundFlow

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
    from datetime import datetime

    from persona_connectors.discord.client import DiscordClient
    from persona_connectors.discord.connector import DiscordConnector
    from persona_connectors.domain.conversation_model import ConversationStateStore
    from persona_connectors.domain.flow import TurnRequest
    from persona_connectors.domain.normalise import NormalisedOutbound
    from persona_connectors.domain.resolution import InboundIdentityResolver

__all__ = ["InboundFlow"]

# Discord's typing indicator expires after ~10 s, so refresh just under that while the
# turn runs (the no-streaming working cue, D-C2-4 carried forward).
_TYPING_REFRESH_SECONDS = 8.0


@contextlib.asynccontextmanager
async def _typing_indicator(client: DiscordClient, channel_id: str) -> AsyncIterator[None]:
    """Show + refresh the Discord typing indicator while the body runs (best-effort).

    Triggers typing immediately and re-triggers every ~8 s (it auto-clears at ~10 s) until
    the context exits; the final reply send clears it. A typing-trigger fault (a transient
    rate-limit / an un-DMable channel) is **suppressed** so a best-effort cue never breaks
    the reply turn; the refresh task is always cancelled on exit. (``suppress(Exception)``
    leaves ``CancelledError`` — a ``BaseException`` — untouched, so cancellation still works.)
    """

    async def _refresh() -> None:
        while True:
            with contextlib.suppress(Exception):
                await client.trigger_typing(channel_id=channel_id)
            await asyncio.sleep(_TYPING_REFRESH_SECONDS)

    task = asyncio.create_task(_refresh())
    try:
        yield
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


class _DiscordFlowTransport:
    """Discord's :class:`FlowTransport` — pure I/O, no auth (see the module docstring).

    Lowers the shared flow's three I/O needs to Discord: a plain system send (to the DM
    channel), the persona reply via the connector (Markdown render + 2000-cp split), and
    the typing working indicator.
    """

    def __init__(self, *, client: DiscordClient, connector: DiscordConnector) -> None:
        self._client = client
        self._connector = connector

    async def send_system(self, *, conversation_key: str, text: str) -> None:
        await self._client.send_message(channel_id=conversation_key, content=text)

    async def send_persona(self, outbound: NormalisedOutbound) -> None:
        await self._connector.send(outbound)

    def typing(self, conversation_key: str) -> contextlib.AbstractAsyncContextManager[None]:
        return _typing_indicator(self._client, conversation_key)


class InboundFlow:
    """Orchestrates one inbound Discord gateway event — the Discord surface over the shared flow.

    All dependencies are injected (DI; no globals). ``bot_user_id`` (resolved at startup via
    ``DiscordClient.get_current_user``) lets the classifier ignore the bot's own echoes
    (loop prevention). The api-coupled callables (``run_turn`` / ``list_persona_names``) are
    owner-scoped by the composition root, keeping this module api-free.
    """

    def __init__(
        self,
        *,
        resolver: InboundIdentityResolver,
        conversation_store: ConversationStateStore,
        connector: DiscordConnector,
        client: DiscordClient,
        list_persona_names: Callable[[str], Mapping[str, Sequence[str]]],
        run_turn: Callable[[TurnRequest], Awaitable[str]],
        now: Callable[[], datetime],
        bot_user_id: str,
    ) -> None:
        self._client = client
        self._now = now
        self._bot_user_id = bot_user_id
        self._transport = _DiscordFlowTransport(client=client, connector=connector)
        self._shared = SharedInboundFlow(
            resolver=resolver,
            conversation_store=conversation_store,
            list_persona_names=list_persona_names,
            run_turn=run_turn,
        )

    async def handle(self, event: dict[str, object]) -> None:
        """Handle one Discord ``MESSAGE_CREATE`` payload (the gateway's ``on_event``)."""
        outcome = classify_message(event, bot_user_id=self._bot_user_id, now=self._now())
        if isinstance(outcome, InboundIgnore):
            return
        if isinstance(outcome, InboundNonText):
            # Non-text → a friendly text-only decline (D-C2-6); no runtime turn.
            await self._client.send_message(
                channel_id=outcome.conversation_key, content=decline_message(outcome.kind)
            )
            return
        # The platform-agnostic sequence (resolve → /new → route → drive → send) is C1's.
        await self._shared.handle_text(outcome.inbound, transport=self._transport)

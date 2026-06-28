"""The Discord connector — C1 ``Connector`` + C0 ``MessageDeliverer`` (Spec C3).

One object that satisfies both seams the framework expects of an adapter:

- **C1's ``Connector``** (``platform`` / ``capabilities`` / :meth:`send` / :meth:`start`
  / :meth:`close`) — :meth:`send` lowers a
  :class:`~persona_connectors.domain.normalise.NormalisedOutbound` to Discord
  message(s) via :func:`~persona_connectors.discord.render.render_outbound` (Markdown
  bold name tag + 2000-code-point splitting) and delivers them, reporting a
  :class:`~persona.delivery.DeliveryResult` — **never a silent drop**: a rate-limit
  (429 / 40003) → ``pending`` (retryable), the **DM-ability gate** (50007 / 50278) →
  ``failed`` with a warm "share a server / message me first" detail (the message stays
  durably persisted), any other rejection → ``failed`` (D-C1-X-platform-rejection /
  D-C3-4).

- **C0's ``MessageDeliverer``** (:meth:`deliver`) — registers into C0's
  ``DeliveryRouter`` under ``"discord"``. The **GAP-A bridge**
  (D-C2-X-gap-a-resolve-channel): a C0 ``OriginatedMessage`` carries only the internal
  ``conversation_id``, so :meth:`deliver` owner-scopes, calls the framework's
  ``ConversationStateStore.resolve_channel`` to get the platform ``channel_key`` (the
  established DM channel), assembles the ``NormalisedOutbound``, and hands off to
  :meth:`send`. **No established DM channel → ``pending``** — the honest C0 gate for
  Discord's conditional DM deliverability (cold outreach to an un-DMable user is never
  assumed delivered; the message stays durable, never lost — D-C3-4).

**api-free** (the thin-adapter / reversibility ideal): it depends only on C1's
owned-surface ports + persona-core contracts + the Discord client. The owner-scope is
injected; the inbound gateway transport is the gateway task's concern (a later ⛔ task).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.delivery import DeliveryOutcome, DeliveryResult

from persona_connectors.discord.client import DISCORD_MAX_MESSAGE_CHARS
from persona_connectors.discord.inbound import PLATFORM
from persona_connectors.discord.render import render_outbound
from persona_connectors.domain.normalise import Capabilities, NormalisedOutbound
from persona_connectors.errors import (
    DiscordApiError,
    DiscordCannotDeliverError,
    DiscordRateLimitError,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from persona.schema.origination import OriginatedMessage

    from persona_connectors.discord.client import DiscordClient
    from persona_connectors.domain.conversation_model import ConversationStateStore

__all__ = ["DISCORD_CAPABILITIES", "DiscordConnector"]

# Discord's channel capabilities (Spec C3 / D-C3-6). Markdown rich formatting + a
# typing affordance + realtime gateway push; speaks as itself (no dedicated author
# slot → the bold-prefix render tier); no WhatsApp-style send window (DM-ability is
# handled in ``send``/``deliver`` outcome mapping, not a capability flag); the 2000
# cap drives the splitter. 1:1 text only in v1 (no threads).
DISCORD_CAPABILITIES = Capabilities(
    supports_rich_formatting=True,
    supports_author_affordance=False,
    supports_threads=False,
    supports_typing_indicator=True,
    is_realtime_push=True,
    can_initiate_freely=True,
    max_body_chars=DISCORD_MAX_MESSAGE_CHARS,
    encoding_sensitive=False,
    requires_delivery_auth=False,
)

# The DM-ability decline (50007 / 50278) — warm, actionable, product voice (D-C3-4).
_CANNOT_DM_DETAIL = "can't reach you on Discord yet — share a server with me, or message me first"


class DiscordConnector:
    """The Discord adapter — implements C1's ``Connector`` + C0's ``MessageDeliverer``.

    Holds no global state. Dependencies (the client, the conversation-state store for
    the GAP-A reverse lookup, and the owner-scope factory) are injected by the
    composition root — keeping this api-free (the reversibility ideal).
    """

    def __init__(
        self,
        *,
        client: DiscordClient,
        conversation_store: ConversationStateStore,
        owner_scope: Callable[[str], AbstractContextManager[None]],
        capabilities: Capabilities = DISCORD_CAPABILITIES,
    ) -> None:
        self.platform = PLATFORM
        self.capabilities = capabilities
        self._client = client
        self._store = conversation_store
        self._owner_scope = owner_scope

    async def send(self, outbound: NormalisedOutbound) -> DeliveryResult:
        """Deliver a reply / originated message to Discord, reporting the outcome.

        Lowers the semantic name tag to Markdown bold + splits to ≤2000 code points
        (render), then sends the part(s) to the DM channel
        (``outbound.conversation_key``). Maps a rate-limit → ``pending`` (retryable),
        the DM-ability gate (50007 / 50278) → ``failed`` (warm detail), any other
        rejection → ``failed`` — **never a silent drop** (D-C1-X-platform-rejection);
        the bot token never reaches the ``detail`` (the client guarantees that).
        """
        parts = render_outbound(outbound.persona, outbound.text)
        try:
            for part in parts:
                await self._client.send_message(channel_id=outbound.conversation_key, content=part)
        except DiscordRateLimitError:
            return DeliveryResult(
                outcome=DeliveryOutcome.PENDING,
                channel=PLATFORM,
                detail="discord rate-limited; retry later",
            )
        except DiscordCannotDeliverError:
            return DeliveryResult(
                outcome=DeliveryOutcome.FAILED, channel=PLATFORM, detail=_CANNOT_DM_DETAIL
            )
        except DiscordApiError:
            return DeliveryResult(
                outcome=DeliveryOutcome.FAILED, channel=PLATFORM, detail="discord send rejected"
            )
        return DeliveryResult(outcome=DeliveryOutcome.DELIVERED, channel=PLATFORM)

    async def deliver(self, message: OriginatedMessage) -> DeliveryResult:
        """Deliver a C0-originated message to Discord (the GAP-A bridge).

        Resolves the originated message's internal ``conversation_id`` to its platform
        DM channel (owner-scoped, via the framework's ``resolve_channel``), assembles a
        ``NormalisedOutbound``, and sends it. No conversation / no established Discord
        DM channel → ``pending`` (durably present, never lost — the C0 no-silent-drop
        contract + Discord's conditional-DM gate, D-C3-4: cold outreach to an un-DMable
        user is never assumed delivered).
        """
        if message.conversation_id is None:
            return DeliveryResult(
                outcome=DeliveryOutcome.PENDING, channel=PLATFORM, detail="no conversation"
            )
        with self._owner_scope(message.owner_user_id):
            ref = self._store.resolve_channel(conversation_id=message.conversation_id)
        if ref is None or ref.platform != PLATFORM:
            return DeliveryResult(
                outcome=DeliveryOutcome.PENDING,
                channel=PLATFORM,
                detail="no established Discord DM channel",
            )
        outbound = NormalisedOutbound(
            persona=message.persona,
            text=message.content,
            conversation_key=ref.channel_key,
            reply_to_message_id=None,
        )
        return await self.send(outbound)

    async def start(self) -> None:
        """No-op — the inbound gateway transport's lifecycle is owned by the service entry.

        The outbound side needs no persistent connection (each send is a stateless REST
        call over the injected client, whose lifecycle the composition root owns).
        Present to satisfy the ``Connector`` protocol; the gateway receive lifecycle is
        the gateway task's concern (a later ⛔ task).
        """

    async def close(self) -> None:
        """No-op — the injected HTTP client's lifecycle is owned by the composition root."""

"""The Slack connector — C1 ``Connector`` + C0 ``MessageDeliverer`` (Spec C3).

One object that satisfies both seams the framework expects of an adapter:

- **C1's ``Connector``** (``platform`` / ``capabilities`` / :meth:`send` / :meth:`start`
  / :meth:`close`) — :meth:`send` lowers a
  :class:`~persona_connectors.domain.normalise.NormalisedOutbound` to Slack message(s) via
  :func:`~persona_connectors.slack.render.render_outbound` (mrkdwn bold name tag +
  readable splitting) and posts them, reporting a
  :class:`~persona.delivery.DeliveryResult` — **never a silent drop**: a rate-limit (429) →
  ``pending`` (retryable), any other rejection → ``failed`` (D-C1-X-platform-rejection).
  **Slack DMs are unconditional** (the app is installed in the workspace), so — unlike
  Discord — there is **no cannot-deliver / DM-ability gate**.

- **C0's ``MessageDeliverer``** (:meth:`deliver`) — registers into C0's ``DeliveryRouter``
  under ``"slack"``. The **GAP-A bridge** (D-C2-X-gap-a-resolve-channel): a C0
  ``OriginatedMessage`` carries only the internal ``conversation_id``, so :meth:`deliver`
  owner-scopes, calls the framework's ``ConversationStateStore.resolve_channel`` to get the
  platform ``channel_key`` (the ``im`` channel), assembles the ``NormalisedOutbound``, and
  hands off to :meth:`send`. No conversation / no connector channel → ``pending`` (never
  lost — the C0 no-silent-drop contract).

**api-free** (the thin-adapter / reversibility ideal): it depends only on C1's
owned-surface ports + persona-core contracts + the Slack client. The owner-scope is
injected; the inbound event transport is the transport's concern (a later ⛔ task).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.delivery import DeliveryOutcome, DeliveryResult

from persona_connectors.domain.normalise import Capabilities, NormalisedOutbound
from persona_connectors.errors import SlackApiError, SlackRateLimitError
from persona_connectors.slack.client import SLACK_MAX_MESSAGE_CHARS
from persona_connectors.slack.inbound import PLATFORM
from persona_connectors.slack.render import render_outbound

if TYPE_CHECKING:
    from collections.abc import Callable
    from contextlib import AbstractContextManager

    from persona.schema.origination import OriginatedMessage

    from persona_connectors.domain.conversation_model import ConversationStateStore
    from persona_connectors.slack.client import SlackClient

__all__ = ["SLACK_CAPABILITIES", "SlackConnector"]

# Slack's channel capabilities (Spec C3 / D-C3-6). mrkdwn rich formatting + realtime push;
# speaks as itself (no dedicated author slot → the bold-prefix render tier); **no bot
# typing indicator for plain DMs** (the no-streaming reply simply sends whole, criterion 7
# "where the platform supports one"); unconditional send (no WhatsApp-style window). 1:1
# text only in v1 (no threads).
SLACK_CAPABILITIES = Capabilities(
    supports_rich_formatting=True,
    supports_author_affordance=False,
    supports_threads=False,
    supports_typing_indicator=False,
    is_realtime_push=True,
    can_initiate_freely=True,
    max_body_chars=SLACK_MAX_MESSAGE_CHARS,
    encoding_sensitive=False,
    requires_delivery_auth=False,
)


class SlackConnector:
    """The Slack adapter — implements C1's ``Connector`` + C0's ``MessageDeliverer``.

    Holds no global state. Dependencies (the client, the conversation-state store for the
    GAP-A reverse lookup, and the owner-scope factory) are injected by the composition root.
    """

    def __init__(
        self,
        *,
        client: SlackClient,
        conversation_store: ConversationStateStore,
        owner_scope: Callable[[str], AbstractContextManager[None]],
        capabilities: Capabilities = SLACK_CAPABILITIES,
    ) -> None:
        self.platform = PLATFORM
        self.capabilities = capabilities
        self._client = client
        self._store = conversation_store
        self._owner_scope = owner_scope

    async def send(self, outbound: NormalisedOutbound) -> DeliveryResult:
        """Deliver a reply / originated message to Slack, reporting the outcome.

        Lowers the semantic name tag to mrkdwn bold + splits (render), then posts the
        part(s) to the ``im`` channel (``outbound.conversation_key``). Maps a rate-limit →
        ``pending`` (retryable), any other rejection → ``failed`` — **never a silent drop**
        (D-C1-X-platform-rejection); the bot token never reaches the ``detail``.
        """
        parts = render_outbound(outbound.persona, outbound.text)
        try:
            for part in parts:
                await self._client.chat_post_message(channel=outbound.conversation_key, text=part)
        except SlackRateLimitError:
            return DeliveryResult(
                outcome=DeliveryOutcome.PENDING,
                channel=PLATFORM,
                detail="slack rate-limited; retry later",
            )
        except SlackApiError:
            return DeliveryResult(
                outcome=DeliveryOutcome.FAILED, channel=PLATFORM, detail="slack send rejected"
            )
        return DeliveryResult(outcome=DeliveryOutcome.DELIVERED, channel=PLATFORM)

    async def deliver(self, message: OriginatedMessage) -> DeliveryResult:
        """Deliver a C0-originated message to Slack (the GAP-A bridge).

        Resolves the originated message's internal ``conversation_id`` to its ``im`` channel
        (owner-scoped, via the framework's ``resolve_channel``), assembles a
        ``NormalisedOutbound``, and sends it. No conversation / no connector channel →
        ``pending`` (durably present, never lost — the C0 no-silent-drop contract).
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
                detail="no connector channel for conversation",
            )
        outbound = NormalisedOutbound(
            persona=message.persona,
            text=message.content,
            conversation_key=ref.channel_key,
            reply_to_message_id=None,
        )
        return await self.send(outbound)

    async def start(self) -> None:
        """No-op — the inbound event transport's lifecycle is owned by the service entry."""

    async def close(self) -> None:
        """No-op — the injected HTTP client's lifecycle is owned by the composition root."""

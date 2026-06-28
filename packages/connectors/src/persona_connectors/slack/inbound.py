"""Inbound normalisation — a Slack ``message.im`` event → C1's shape (Spec C3).

The adapter's job at the front of the flow: take a Slack Events API ``message`` event and
classify it into one of three pure outcomes the shared flow branches on —

- :class:`InboundText` — a DM text message, carried as a C1
  :class:`~persona_connectors.domain.normalise.NormalisedInbound`. A command (``/new``)
  is still *text*; the shared flow's command parser inspects ``.text``.
- :class:`InboundNonText` — a file / rich attachment, classified to a small
  :class:`SlackNonTextKind` so the flow renders the friendly text-only decline.
- :class:`InboundIgnore` — a **non-``im`` (channel/group) message** (DM-only enforcement,
  D-C3-5), a bot's / the app's own message (loop prevention), an edit/system subtype, or a
  malformed/empty payload; silently skipped.

**DM-only (D-C3-5):** act only on ``channel_type == "im"`` — channels/groups/mpim are the
parked public model. **Loop prevention:** ignore any ``bot_id``-bearing message and the
app's own (``user == bot_user_id``). **The identity mapping (D-C1-5):** ``user`` →
``sender_id`` (the key that drives linking + resolution) and ``channel`` → ``conversation_key``
(the ``im`` channel to reply on). Slack's ``ts`` is the per-message id **and** a Unix
timestamp → a **tz-aware UTC** ``received_at`` (the everywhere-aware rule; ingestion-time
fallback when absent/unparseable).

**Non-text taxonomy is Slack-LOCAL (the rule-of-three divergence).** Slack has no clean
"voice message" primitive (audio is just a file with an audio mimetype — unlike Discord's
voice flag / Telegram's ``voice`` type), so the kinds are ``media`` (files) + ``unknown``
(rich attachments without text), NOT Discord's ``{voice, media, unknown}``. The shared
decline *copy* (:mod:`persona_connectors.domain.system_replies`) is reused; the *kind*
stays local because it genuinely differs.

Pure + api-free: deterministic over its input (``now`` + ``bot_user_id`` injected).
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from persona_connectors.domain.normalise import NormalisedInbound

__all__ = [
    "PLATFORM",
    "InboundIgnore",
    "InboundNonText",
    "InboundText",
    "NormalisedEvent",
    "SlackNonTextKind",
    "classify_event",
]

# The opaque platform key carried on every NormalisedInbound + the DeliveryRouter
# registration key (D-08-3 — never branched on by the framework).
PLATFORM = "slack"

# Subtypes that are edits / system / bot posts (not a fresh user message) — ignored.
# ``file_share`` is deliberately NOT here: it is a real user upload → a non-text decline.
_IGNORED_SUBTYPES = frozenset(
    {
        "message_changed",
        "message_deleted",
        "message_replied",
        "thread_broadcast",
        "bot_message",
        "channel_join",
        "channel_leave",
        "channel_topic",
        "channel_purpose",
        "channel_name",
        "channel_archive",
        "channel_unarchive",
    }
)


class SlackNonTextKind(StrEnum):
    """The class of non-text content, driving the friendly decline (D-C2-6 carried forward).

    Slack-local + deliberately WITHOUT ``voice`` (Slack has no clean voice primitive — the
    rule-of-three divergence from Discord): ``media`` (an uploaded file) and ``unknown``
    (rich attachments without text). The flow maps each to the shared decline copy.
    """

    media = "media"
    unknown = "unknown"


class InboundText(BaseModel):
    """A DM text message normalised to C1's inbound shape — drives the shared flow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inbound: NormalisedInbound


class InboundNonText(BaseModel):
    """Non-text content — declined gracefully (D-C2-6), never a runtime turn."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SlackNonTextKind
    conversation_key: str
    sender_id: str
    message_id: str


class InboundIgnore(BaseModel):
    """An event with nothing to act on — silently skipped (no reply)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str


# The three outcomes the flow branches on.
NormalisedEvent = InboundText | InboundNonText | InboundIgnore


def _received_at(event: dict[str, object], *, fallback: datetime) -> datetime:
    """Convert Slack's ``ts`` (a Unix ``seconds.micros`` string) to tz-aware UTC."""
    ts = event.get("ts")
    if isinstance(ts, str) and ts:
        try:
            return datetime.fromtimestamp(float(ts), tz=UTC)
        except (ValueError, OSError):
            return fallback
    return fallback


def _nonempty_list(value: object) -> bool:
    """Whether ``value`` is a non-empty list (files / attachments present)."""
    return isinstance(value, list) and len(value) > 0


def classify_event(event: dict[str, object], *, bot_user_id: str, now: datetime) -> NormalisedEvent:
    """Classify a Slack ``message`` event into a :data:`NormalisedEvent` (pure).

    Args:
        event: The decoded Slack ``message`` event (the inner event, envelope unwrapped).
        bot_user_id: The app's own Slack user id — its echoes are ignored (loop prevention).
        now: Tz-aware UTC ingestion time — the fallback when ``ts`` is absent/unparseable.

    Returns:
        :class:`InboundText` for a DM text message, :class:`InboundNonText` for a file /
        rich attachment, or :class:`InboundIgnore` for a non-``im`` / bot / own / edit /
        malformed / empty event.
    """
    if event.get("type") != "message":
        return InboundIgnore(reason="not-a-message")
    if event.get("channel_type") != "im":
        return InboundIgnore(reason="not-a-dm")  # DM-only (D-C3-5)
    if event.get("bot_id") is not None:
        return InboundIgnore(reason="bot-message")  # loop prevention

    user = event.get("user")
    if not isinstance(user, str) or not user:
        return InboundIgnore(reason="no-user")
    if user == bot_user_id:
        return InboundIgnore(reason="own-message")  # loop prevention

    subtype = event.get("subtype")
    if isinstance(subtype, str) and subtype in _IGNORED_SUBTYPES:
        return InboundIgnore(reason=f"subtype-{subtype}")

    channel = event.get("channel")
    ts = event.get("ts")
    if not isinstance(channel, str) or not channel or not isinstance(ts, str) or not ts:
        return InboundIgnore(reason="malformed-event")

    # A file upload is non-text even if it carries a caption (the C2 photo-caption rule).
    if _nonempty_list(event.get("files")):
        return InboundNonText(
            kind=SlackNonTextKind.media, conversation_key=channel, sender_id=user, message_id=ts
        )

    text = event.get("text")
    if isinstance(text, str) and text.strip():
        raw: dict[str, str] = {"platform": PLATFORM, "channel": channel}
        team_id = event.get("team")
        if isinstance(team_id, str) and team_id:
            raw["team_id"] = team_id
        inbound = NormalisedInbound(
            platform=PLATFORM,
            sender_id=user,
            conversation_key=channel,
            message_id=ts,
            text=text,
            received_at=_received_at(event, fallback=now),
            raw=raw,
        )
        return InboundText(inbound=inbound)

    if _nonempty_list(event.get("attachments")):
        return InboundNonText(
            kind=SlackNonTextKind.unknown, conversation_key=channel, sender_id=user, message_id=ts
        )
    return InboundIgnore(reason="empty-event")

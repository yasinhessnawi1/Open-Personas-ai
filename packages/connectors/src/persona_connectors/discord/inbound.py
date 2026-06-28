"""Inbound normalisation — a Discord ``MESSAGE_CREATE`` → C1's shape (Spec C3).

The adapter's job at the front of the flow: take a Discord gateway message object and
classify it into one of three pure outcomes the shared flow branches on —

- :class:`InboundText` — a DM text message, carried as a C1
  :class:`~persona_connectors.domain.normalise.NormalisedInbound`. A command
  (``/new``) is still *text*; the shared flow's command parser inspects ``.text``.
- :class:`InboundNonText` — voice / attachment / sticker content, classified to a
  small :class:`DiscordNonTextKind` so the flow renders the friendly text-only
  decline (D-C2-6 carried forward); it carries just enough to reply.
- :class:`InboundIgnore` — a **guild/server message** (DM-only enforcement, D-C3-5),
  the bot's own / another bot's message (loop prevention), or a malformed/empty
  payload; silently skipped, no reply.

**DM-only (D-C3-5):** a Discord DM has **no ``guild_id``** (the channel is a 1:1 DM);
a message carrying ``guild_id`` is in a server and is ignored — the persona is reached
only in DMs (the personal model; channels are the parked public model). **Loop
prevention:** the bot's own ``MESSAGE_CREATE`` echoes (``author.id == bot_user_id``)
and any other bot (``author.bot``) are ignored.

**The identity mapping (D-C1-5):** ``author.id`` → ``sender_id`` (the key that drives
linking + resolution) and ``channel_id`` → ``conversation_key`` (the DM channel to
reply on). Discord's ISO-8601 ``timestamp`` → a **tz-aware UTC** datetime (the
everywhere-aware rule; ingestion-time fallback when absent/unparseable).

Pure + api-free: deterministic over its input (``now`` + ``bot_user_id`` injected),
no I/O, no ``persona_api``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from persona_connectors.domain.normalise import NormalisedInbound

__all__ = [
    "PLATFORM",
    "DiscordNonTextKind",
    "InboundIgnore",
    "InboundNonText",
    "InboundText",
    "NormalisedUpdate",
    "classify_message",
]

# The opaque platform key carried on every NormalisedInbound + the DeliveryRouter
# registration key (D-08-3 — never branched on by the framework).
PLATFORM = "discord"

# Discord message flag bit for a voice message (IS_VOICE_MESSAGE = 1 << 13).
_VOICE_MESSAGE_FLAG = 1 << 13
# Content fields that mean "non-text user content" when there's no text body.
_MEDIA_KEYS = ("attachments", "sticker_items", "stickers", "embeds")


class DiscordNonTextKind(StrEnum):
    """The class of non-text content, driving the friendly decline (D-C2-6 carried forward).

    Coarse on purpose: ``voice`` (a Discord voice message), ``media`` (attachments /
    stickers / embeds), and ``unknown`` (any other unsupported content) — the flow
    maps each to a product-voice line; the framework is text-only in v1.
    """

    voice = "voice"
    media = "media"
    unknown = "unknown"


class InboundText(BaseModel):
    """A DM text message normalised to C1's inbound shape — drives the shared flow."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    inbound: NormalisedInbound


class InboundNonText(BaseModel):
    """Non-text content — declined gracefully (D-C2-6), never a runtime turn.

    Carries only what a decline reply needs: where to send it (``conversation_key``),
    the message it replies to (``message_id``), the sender, and the kind.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DiscordNonTextKind
    conversation_key: str
    sender_id: str
    message_id: str


class InboundIgnore(BaseModel):
    """An update with nothing to act on — silently skipped (no reply).

    Attributes:
        reason: A short tag for observability (``"guild-message"`` /
            ``"own-or-bot-message"`` / ``"malformed-message"`` / ``"empty-message"``).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    reason: str


# The three outcomes the flow branches on.
NormalisedUpdate = InboundText | InboundNonText | InboundIgnore


def _as_dict(value: object) -> dict[str, object] | None:
    """Narrow a JSON value to an object, else ``None`` (defensive over raw payloads)."""
    return value if isinstance(value, dict) else None


def _id_str(value: object) -> str | None:
    """Stringify a Discord snowflake (string, or defensively int); ``None`` if absent/wrong."""
    if isinstance(value, bool):  # bool is an int subclass — never an id
        return None
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str) and value:
        return value
    return None


def _received_at(message: dict[str, object], *, fallback: datetime) -> datetime:
    """Convert Discord's ISO-8601 ``timestamp`` to tz-aware UTC (ingestion-time fallback)."""
    raw = message.get("timestamp")
    if isinstance(raw, str) and raw:
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError:
            return fallback
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    return fallback


def _display_name(author: dict[str, object]) -> str | None:
    """Prefer the global display name, else the username, else ``None``."""
    for key in ("global_name", "username"):
        value = author.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _reply_to_id(message: dict[str, object]) -> str | None:
    """Extract the replied-to message id from ``message_reference``, if this is a reply."""
    reference = _as_dict(message.get("message_reference"))
    return _id_str(reference.get("message_id")) if reference is not None else None


def _has_media(message: dict[str, object]) -> bool:
    """Whether the message carries any non-empty media list (attachment/sticker/embed)."""
    return any(isinstance(message.get(key), list) and message.get(key) for key in _MEDIA_KEYS)


def _non_text_kind(message: dict[str, object]) -> DiscordNonTextKind:
    """Classify a no-text message's content (voice flag → voice; media lists → media)."""
    flags = message.get("flags")
    if isinstance(flags, int) and not isinstance(flags, bool) and flags & _VOICE_MESSAGE_FLAG:
        return DiscordNonTextKind.voice
    if _has_media(message):
        return DiscordNonTextKind.media
    return DiscordNonTextKind.unknown


def classify_message(
    message: dict[str, object], *, bot_user_id: str, now: datetime
) -> NormalisedUpdate:
    """Classify a Discord ``MESSAGE_CREATE`` payload into a :data:`NormalisedUpdate` (pure).

    Args:
        message: The decoded Discord message object (the gateway dispatch ``d``).
        bot_user_id: The bot's own user id — its echoes are ignored (loop prevention).
        now: Tz-aware UTC ingestion time — the fallback when the message ``timestamp``
            is absent/unparseable (the everywhere-aware rule; injected so this is pure).

    Returns:
        :class:`InboundText` for a DM text message, :class:`InboundNonText` for
        voice/attachment content, or :class:`InboundIgnore` for a guild/own/bot/
        malformed/empty message.
    """
    author = _as_dict(message.get("author"))
    sender_id = _id_str(author.get("id")) if author is not None else None
    if author is None or sender_id is None:
        return InboundIgnore(reason="malformed-message")

    # Loop prevention: ignore the bot's own echoes + any other bot (D-C3-5).
    if author.get("bot") is True or sender_id == bot_user_id:
        return InboundIgnore(reason="own-or-bot-message")

    # DM-only enforcement (D-C3-5): a DM has NO guild_id; a server message is ignored.
    if message.get("guild_id") is not None:
        return InboundIgnore(reason="guild-message")

    conversation_key = _id_str(message.get("channel_id"))
    message_id = _id_str(message.get("id"))
    if conversation_key is None or message_id is None:
        return InboundIgnore(reason="malformed-message")

    content = message.get("content")
    if isinstance(content, str) and content.strip():
        raw: dict[str, str] = {"platform": PLATFORM, "channel_id": conversation_key}
        inbound = NormalisedInbound(
            platform=PLATFORM,
            sender_id=sender_id,
            conversation_key=conversation_key,
            message_id=message_id,
            text=content,
            received_at=_received_at(message, fallback=now),
            reply_to_message_id=_reply_to_id(message),
            display_name=_display_name(author),
            raw=raw,
        )
        return InboundText(inbound=inbound)

    # No text body: voice / media → a friendly decline; truly empty → ignore.
    if message.get("flags") or _has_media(message):
        return InboundNonText(
            kind=_non_text_kind(message),
            conversation_key=conversation_key,
            sender_id=sender_id,
            message_id=message_id,
        )
    return InboundIgnore(reason="empty-message")

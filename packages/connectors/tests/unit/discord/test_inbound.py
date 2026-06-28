"""Discord inbound classification (Spec C3) — DM-only + non-text + identity mapping.

Proves the load-bearing rules: a DM (no ``guild_id``) → ``NormalisedInbound``; a
guild/server message → ignored (DM-only, D-C3-5); the bot's own + other bots →
ignored (loop prevention); voice/attachment → a non-text decline; ``author.id`` →
``sender_id`` and ``channel_id`` → ``conversation_key``; the ISO-8601 timestamp →
tz-aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

from persona_connectors.discord.inbound import (
    PLATFORM,
    DiscordNonTextKind,
    InboundIgnore,
    InboundNonText,
    InboundText,
    classify_message,
)

_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
_BOT = "bot1"


def _msg(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "id": "msg-9",
        "channel_id": "dm-5",
        "author": {"id": "user-7", "username": "Yasin"},
        "content": "Astrid, hello",
        "timestamp": "2026-06-27T12:00:00.000000+00:00",
    }
    base.update(overrides)
    return base


# --- the happy DM path ---


def test_dm_text_normalises() -> None:
    outcome = classify_message(_msg(), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundText)
    nb = outcome.inbound
    assert nb.platform == PLATFORM
    assert nb.sender_id == "user-7"  # author.id → the identity key
    assert nb.conversation_key == "dm-5"  # channel_id → the DM channel
    assert nb.message_id == "msg-9"
    assert nb.text == "Astrid, hello"
    assert nb.received_at == datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
    assert nb.received_at.tzinfo is not None


def test_display_name_prefers_global_name() -> None:
    msg = _msg(author={"id": "user-7", "username": "yasin99", "global_name": "Yasin H"})
    outcome = classify_message(msg, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundText)
    assert outcome.inbound.display_name == "Yasin H"


def test_reply_reference_is_extracted() -> None:
    msg = _msg(message_reference={"message_id": "msg-3"})
    outcome = classify_message(msg, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundText)
    assert outcome.inbound.reply_to_message_id == "msg-3"


def test_unparseable_timestamp_falls_back_to_now() -> None:
    outcome = classify_message(_msg(timestamp="not-a-date"), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundText)
    assert outcome.inbound.received_at == _NOW


# --- DM-only enforcement (D-C3-5) ---


def test_guild_message_is_ignored() -> None:
    """A message carrying guild_id is in a server → ignored (the personal model)."""
    outcome = classify_message(_msg(guild_id="guild-1"), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "guild-message"


# --- loop prevention ---


def test_own_message_is_ignored() -> None:
    msg = _msg(author={"id": _BOT, "username": "PersonaBot"})
    outcome = classify_message(msg, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "own-or-bot-message"


def test_other_bot_message_is_ignored() -> None:
    msg = _msg(author={"id": "other-bot", "username": "Spammer", "bot": True})
    outcome = classify_message(msg, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "own-or-bot-message"


# --- non-text → graceful decline ---


def test_voice_message_is_non_text_voice() -> None:
    msg = _msg(content="", flags=1 << 13)
    outcome = classify_message(msg, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundNonText)
    assert outcome.kind is DiscordNonTextKind.voice
    assert outcome.conversation_key == "dm-5"


def test_attachment_only_is_non_text_media() -> None:
    msg = _msg(content="", attachments=[{"id": "a1", "filename": "cat.png"}])
    outcome = classify_message(msg, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundNonText)
    assert outcome.kind is DiscordNonTextKind.media


# --- ignore edges ---


def test_empty_message_is_ignored() -> None:
    outcome = classify_message(_msg(content=""), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "empty-message"


def test_whitespace_only_content_is_ignored() -> None:
    outcome = classify_message(_msg(content="   "), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)


def test_missing_author_is_malformed() -> None:
    msg = _msg()
    del msg["author"]
    outcome = classify_message(msg, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "malformed-message"

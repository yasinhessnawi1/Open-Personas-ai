"""Slack inbound classification (Spec C3) — im-only + loop-prevention + non-text + mapping.

Proves: an ``im`` text message → ``NormalisedInbound``; a channel/group message → ignored
(DM-only, D-C3-5); bot/own/edit-subtype → ignored (loop prevention); a file → a non-text
``media`` decline; ``user`` → ``sender_id`` and ``channel`` → ``conversation_key``; the
``ts`` → tz-aware UTC.
"""

from __future__ import annotations

from datetime import UTC, datetime

from persona_connectors.slack.inbound import (
    PLATFORM,
    InboundIgnore,
    InboundNonText,
    InboundText,
    SlackNonTextKind,
    classify_event,
)

_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
_BOT = "U_BOT"
_TS = "1700000000.000100"


def _event(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "type": "message",
        "channel_type": "im",
        "channel": "D5",
        "user": "U7",
        "text": "Astrid, hello",
        "ts": _TS,
        "team": "T1",
    }
    base.update(overrides)
    return base


def test_im_text_normalises() -> None:
    outcome = classify_event(_event(), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundText)
    nb = outcome.inbound
    assert nb.platform == PLATFORM
    assert nb.sender_id == "U7"  # user → identity key
    assert nb.conversation_key == "D5"  # channel → the im channel
    assert nb.message_id == _TS
    assert nb.text == "Astrid, hello"
    assert nb.received_at.tzinfo is not None
    assert nb.received_at == datetime.fromtimestamp(float(_TS), tz=UTC)
    assert nb.raw["team_id"] == "T1"


def test_unparseable_ts_falls_back_to_now() -> None:
    outcome = classify_event(_event(ts="not-a-ts"), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundText)
    assert outcome.inbound.received_at == _NOW


# --- DM-only (D-C3-5) ---


def test_channel_message_is_ignored() -> None:
    outcome = classify_event(_event(channel_type="channel"), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "not-a-dm"


# --- loop prevention ---


def test_bot_message_is_ignored() -> None:
    outcome = classify_event(_event(bot_id="B1"), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "bot-message"


def test_own_message_is_ignored() -> None:
    outcome = classify_event(_event(user=_BOT), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "own-message"


def test_edit_subtype_is_ignored() -> None:
    outcome = classify_event(_event(subtype="message_changed"), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason.startswith("subtype-")


# --- non-text declines (no voice kind — Slack-local) ---


def test_file_upload_is_non_text_media_even_with_a_caption() -> None:
    event = _event(text="here you go", files=[{"id": "F1", "mimetype": "image/png"}])
    outcome = classify_event(event, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundNonText)
    assert outcome.kind is SlackNonTextKind.media


def test_attachments_without_text_is_non_text_unknown() -> None:
    event = _event(text="", attachments=[{"text": "rich"}])
    outcome = classify_event(event, bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundNonText)
    assert outcome.kind is SlackNonTextKind.unknown


# --- ignore edges ---


def test_empty_message_is_ignored() -> None:
    outcome = classify_event(_event(text="   "), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "empty-event"


def test_non_message_type_is_ignored() -> None:
    outcome = classify_event(_event(type="reaction_added"), bot_user_id=_BOT, now=_NOW)
    assert isinstance(outcome, InboundIgnore)
    assert outcome.reason == "not-a-message"

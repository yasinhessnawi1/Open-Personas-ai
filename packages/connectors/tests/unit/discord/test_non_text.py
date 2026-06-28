"""Discord non-text declines (Spec C3) — total over the kind enum, shared copy."""

from __future__ import annotations

from persona_connectors.discord.inbound import DiscordNonTextKind
from persona_connectors.discord.non_text import decline_message
from persona_connectors.domain.system_replies import DECLINE_MEDIA, DECLINE_UNKNOWN, DECLINE_VOICE


def test_voice_decline() -> None:
    assert decline_message(DiscordNonTextKind.voice) == DECLINE_VOICE
    assert "voice" in decline_message(DiscordNonTextKind.voice).lower()


def test_media_decline() -> None:
    assert decline_message(DiscordNonTextKind.media) == DECLINE_MEDIA


def test_unknown_decline() -> None:
    assert decline_message(DiscordNonTextKind.unknown) == DECLINE_UNKNOWN


def test_every_kind_has_a_decline() -> None:
    """Total over the enum — no kind falls through (the assert_never guard)."""
    for kind in DiscordNonTextKind:
        assert decline_message(kind)

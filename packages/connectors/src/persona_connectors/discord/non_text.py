"""Non-text graceful declines for Discord (Spec C3, D-C2-6 carried forward).

When :func:`~persona_connectors.discord.inbound.classify_message` yields an
:class:`~persona_connectors.discord.inbound.InboundNonText`, the flow replies with a
friendly, text-only-for-now line rather than an error or silence. The line is the
**bot speaking** (system-level), not a persona — plain text, no persona tag, no
runtime turn.

The decline **copy** is platform-neutral and shared
(:mod:`persona_connectors.domain.system_replies`); only the per-platform non-text
**kind** is local (:class:`~persona_connectors.discord.inbound.DiscordNonTextKind`).
Pure + api-free: a total function over the enum (``assert_never`` guarantees every
kind is handled).
"""

from __future__ import annotations

from typing import assert_never

from persona_connectors.discord.inbound import DiscordNonTextKind
from persona_connectors.domain.system_replies import (
    DECLINE_MEDIA,
    DECLINE_UNKNOWN,
    DECLINE_VOICE,
)

__all__ = ["decline_message"]


def decline_message(kind: DiscordNonTextKind) -> str:
    """Return the friendly text-only decline for a Discord non-text message (D-C2-6).

    Args:
        kind: The classified non-text content kind.

    Returns:
        A single product-voice line (the shared copy) making clear the persona works
        over text for now.
    """
    match kind:
        case DiscordNonTextKind.voice:
            return DECLINE_VOICE
        case DiscordNonTextKind.media:
            return DECLINE_MEDIA
        case DiscordNonTextKind.unknown:
            return DECLINE_UNKNOWN
        case _:  # pragma: no cover - exhaustiveness guard (mypy assert_never)
            assert_never(kind)

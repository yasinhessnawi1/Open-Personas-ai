"""Non-text graceful declines for Slack (Spec C3, D-C2-6 carried forward).

When :func:`~persona_connectors.slack.inbound.classify_event` yields an
:class:`~persona_connectors.slack.inbound.InboundNonText`, the flow replies with a friendly,
text-only-for-now line rather than an error or silence. The line is the **bot speaking**
(system-level), not a persona — plain text, no persona tag, no runtime turn.

The decline **copy** is platform-neutral and shared
(:mod:`persona_connectors.domain.system_replies`); only the per-platform non-text **kind**
is local (:class:`~persona_connectors.slack.inbound.SlackNonTextKind` — ``media`` /
``unknown``, no ``voice``). Pure + api-free: a total function over the enum.
"""

from __future__ import annotations

from typing import assert_never

from persona_connectors.domain.system_replies import DECLINE_MEDIA, DECLINE_UNKNOWN
from persona_connectors.slack.inbound import SlackNonTextKind

__all__ = ["decline_message"]


def decline_message(kind: SlackNonTextKind) -> str:
    """Return the friendly text-only decline for a Slack non-text message (D-C2-6)."""
    match kind:
        case SlackNonTextKind.media:
            return DECLINE_MEDIA
        case SlackNonTextKind.unknown:
            return DECLINE_UNKNOWN
        case _:  # pragma: no cover - exhaustiveness guard (mypy assert_never)
            assert_never(kind)

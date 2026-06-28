"""System-reply copy for the Telegram flow — re-exported from the shared surface.

The "bot speaking" replies (the list-and-instructions first-contact, the ``/new``
confirmations, the no-personas edge) are **platform-neutral plain text**, so they
now live in the framework's owned surface (:mod:`persona_connectors.domain.system_replies`,
D-C3-X-flow-skeleton) and every text adapter reuses them. This module re-exports
them under their historical names so existing Telegram importers + tests keep
working (the C3 amendment #2 re-point, additive — no behaviour change).
"""

from __future__ import annotations

from persona_connectors.domain.system_replies import (
    NEW_CONVERSATION_MESSAGE,
    NO_ACTIVE_TO_RESET_MESSAGE,
    NO_PERSONAS_MESSAGE,
    render_list_and_instructions,
)

__all__ = [
    "NEW_CONVERSATION_MESSAGE",
    "NO_ACTIVE_TO_RESET_MESSAGE",
    "NO_PERSONAS_MESSAGE",
    "render_list_and_instructions",
]

"""Outbound rendering for Discord (Spec C3) — Markdown wrap over the shared splitter.

Two pure concerns turn a persona reply into Discord message(s):

- **Splitting (D-C3-6).** Discord caps a message at **2000 characters**, counted in
  **Unicode code points** (C3-R-1), and — unlike Telegram — the markup characters
  count toward that budget (Discord doesn't parse them out). The boundary-aware split
  is the shared :func:`persona_connectors.domain.render.split_text` (D-C3-X-splitter)
  bound to the **code-point** measure.
- **Rendering (D-C3-6).** :func:`render_outbound` lowers C0's semantic
  :class:`~persona.schema.origination.PersonaIdentityTag` to Discord's **bold-prefix**
  render tier (C1-D-6): a ``**Name**`` header on the **first part only**. The body is
  sent **as-is** — Discord renders Markdown and there is no HTML-style injection risk
  (a cosmetic mis-render of stray ``*``/``_`` is acceptable in v1; the name is the
  only wrapped span). A richer embed-``author`` slot is a later enhancement (spec §2).

Rendering (the Markdown wrap) is Discord-specific and stays here; only the split +
the length measure are shared. Pure + api-free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona_connectors.discord.client import DISCORD_MAX_MESSAGE_CHARS
from persona_connectors.domain.render import codepoint_measure, split_text

if TYPE_CHECKING:
    from persona.schema.origination import PersonaIdentityTag

__all__ = ["render_outbound"]

# The header ``**Name**\n`` occupies ``len(name)`` + 4 (the two ``**`` pairs) + 1 (the
# newline) code points of the 2000 budget — Discord counts markup, so reserve it.
_HEADER_OVERHEAD = 5


def render_outbound(
    persona: PersonaIdentityTag,
    text: str,
    *,
    budget: int = DISCORD_MAX_MESSAGE_CHARS,
) -> list[str]:
    """Render a persona reply to Discord Markdown message part(s) (D-C3-6).

    Lowers the semantic name tag to the bold-prefix tier: a ``**Name**`` header on the
    first part only. Splits the body against the 2000-code-point budget (the first part
    reserving room for the header), body sent as-is (Discord renders Markdown).

    Args:
        persona: The originating persona's identity tag (the SEMANTIC tag, C1-D-6).
        text: The plain reply body.
        budget: The per-message code-point budget (defaults to Discord's 2000).

    Returns:
        The ordered list of message strings to send (at least one — a header-only
        message when the body is empty).
    """
    name = persona.display_name
    header = f"**{name}**"
    reserve = codepoint_measure(name) + _HEADER_OVERHEAD
    first_budget = max(1, budget - reserve)

    body_chunks = split_text(
        text, budget=budget, first_budget=first_budget, measure=codepoint_measure
    )
    if not body_chunks:
        return [header]
    messages: list[str] = []
    for index, chunk in enumerate(body_chunks):
        messages.append(f"{header}\n{chunk}" if index == 0 else chunk)
    return messages

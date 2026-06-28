"""Outbound rendering for Slack (Spec C3) — mrkdwn wrap over the shared splitter.

Two pure concerns turn a persona reply into Slack message(s):

- **Splitting (D-C3-6).** Slack's hard ``text`` cap is 40000 characters, but a single huge
  message reads poorly, so the reply is split at a far smaller, readable budget. The
  boundary-aware split is the shared :func:`persona_connectors.domain.render.split_text`
  (D-C3-X-splitter) bound to the **code-point** measure.
- **Rendering (D-C3-6).** :func:`render_outbound` lowers C0's semantic
  :class:`~persona.schema.origination.PersonaIdentityTag` to Slack's **bold-prefix** render
  tier (C1-D-6): a ``*Name*`` header (Slack mrkdwn bold is a **single** asterisk — ``**``
  renders literally, the naive-port bug) on the **first part only**. The name + body are
  **mrkdwn-escaped** (only ``& < >`` — Slack's three reserved chars), splitting the
  plaintext first then escaping each part so an entity never tears across a boundary.

Rendering (the mrkdwn wrap + escaping) is Slack-specific and stays here; only the split +
the length measure are shared. Pure + api-free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona_connectors.domain.render import codepoint_measure, split_text

if TYPE_CHECKING:
    from persona.schema.origination import PersonaIdentityTag

__all__ = ["SLACK_SPLIT_BUDGET", "escape_mrkdwn", "render_outbound"]

# A readable per-message split budget — well under Slack's 40000 hard cap.
SLACK_SPLIT_BUDGET = 3500


def escape_mrkdwn(text: str) -> str:
    """Escape the three characters Slack mrkdwn reserves (``&`` first, then ``<``/``>``)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def render_outbound(
    persona: PersonaIdentityTag,
    text: str,
    *,
    budget: int = SLACK_SPLIT_BUDGET,
) -> list[str]:
    """Render a persona reply to Slack mrkdwn message part(s) (D-C3-6).

    Lowers the semantic name tag to the bold-prefix tier: a ``*Name*`` header on the first
    part only, name + body mrkdwn-escaped. Splits the **plaintext** against the budget (the
    first part reserving room for the header), then escapes each part — so an entity never
    tears across a boundary.

    Args:
        persona: The originating persona's identity tag (the SEMANTIC tag, C1-D-6).
        text: The plain reply body.
        budget: The per-message code-point budget (defaults to a readable ~3500).

    Returns:
        The ordered list of mrkdwn message strings to send (at least one — a header-only
        message when the body is empty).
    """
    header = f"*{escape_mrkdwn(persona.display_name)}*"
    reserve = codepoint_measure(header) + 1  # the header + the newline before the body
    first_budget = max(1, budget - reserve)

    body_chunks = split_text(
        text, budget=budget, first_budget=first_budget, measure=codepoint_measure
    )
    if not body_chunks:
        return [header]
    messages: list[str] = []
    for index, chunk in enumerate(body_chunks):
        escaped = escape_mrkdwn(chunk)
        messages.append(f"{header}\n{escaped}" if index == 0 else escaped)
    return messages

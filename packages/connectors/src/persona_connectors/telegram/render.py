"""Outbound rendering for Telegram (Spec C2 T3) — HTML wrap over the shared splitter.

Two pure concerns turn a persona reply into Telegram message(s):

- **Splitting (D-C2-3).** Telegram caps a message at **4096 characters "after
  entities parsing"** — the *visible* text length in **UTF-16 code units** (an
  emoji / astral char counts as 2; HTML tags don't count, they're parsed out). The
  boundary-aware split algorithm now lives in the framework's owned surface
  (:func:`persona_connectors.domain.render.split_text`, D-C3-X-splitter — the
  "reusable C3/C4" splitter D-C2-3 intended); this module binds it to Telegram's
  **UTF-16** measure via :func:`utf16_length` and the local :func:`split_text`
  wrapper, preserving the Telegram signature + behaviour byte-for-byte.
- **Rendering (D-C2-5).** :func:`render_outbound` lowers C0's semantic
  :class:`~persona.schema.origination.PersonaIdentityTag` to Telegram's
  **bold-prefix** render tier (C1-D-6): a ``<b>Name</b>`` header on the **first
  part only**, name + body **HTML-escaped** (``& < >``). It splits the **plaintext
  first, then wraps** each part, so an HTML tag can never tear across a boundary.

Rendering (the HTML wrap + escaping) is Telegram-specific and stays here; only the
platform-agnostic split + the length measure are shared (C1-D-6: core never carries
platform markup). This module is **pure + api-free**.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona_connectors.domain.render import split_text as _split_text
from persona_connectors.domain.render import utf16_measure
from persona_connectors.telegram.client import TELEGRAM_MAX_MESSAGE_CHARS

if TYPE_CHECKING:
    from persona.schema.origination import PersonaIdentityTag

__all__ = [
    "PARSE_MODE_HTML",
    "escape_html",
    "render_outbound",
    "split_text",
    "utf16_length",
]

# Telegram's HTML parse mode (D-C2-5) — escapes only ``& < >`` (3 chars), far
# safer over arbitrary persona text than MarkdownV2's ~18-char escape set.
PARSE_MODE_HTML = "HTML"

# Telegram counts its 4096 cap in UTF-16 code units; the shared splitter's
# ``utf16_measure`` IS that count. Aliased under the historical name so existing
# importers (``telegram/__init__`` + tests) keep working (D-C3-X-splitter).
utf16_length = utf16_measure


def escape_html(text: str) -> str:
    """Escape the three characters Telegram HTML requires (``&`` first, then ``<``/``>``)."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def split_text(
    text: str, *, budget: int = TELEGRAM_MAX_MESSAGE_CHARS, first_budget: int | None = None
) -> list[str]:
    """Split ``text`` into ≤``budget`` UTF-16-unit chunks on natural boundaries (D-C2-3).

    A thin Telegram binding over the shared
    :func:`persona_connectors.domain.render.split_text`: it fixes the measure to
    UTF-16 (Telegram's unit) and defaults the budget to Telegram's 4096, preserving
    this module's original signature + behaviour. ``first_budget`` reserves room for
    a name header on the first chunk.

    Raises:
        ValueError: ``budget`` (or a provided ``first_budget``) is below 1.
    """
    return _split_text(text, budget=budget, first_budget=first_budget, measure=utf16_measure)


def render_outbound(
    persona: PersonaIdentityTag,
    text: str,
    *,
    budget: int = TELEGRAM_MAX_MESSAGE_CHARS,
) -> list[str]:
    """Render a persona reply to Telegram HTML message part(s) (D-C2-5 + D-C2-3).

    Lowers the semantic name tag to the bold-prefix tier: a ``<b>Name</b>`` header
    on the first part only, name + body HTML-escaped. Splits the **plaintext**
    against the UTF-16 budget (the first part reserving room for the header), then
    wraps each part — so a tag never tears across a message boundary.

    Args:
        persona: The originating persona's identity tag (the SEMANTIC tag, C1-D-6).
        text: The plain reply body (markup-free).
        budget: The per-message UTF-16 budget (defaults to Telegram's 4096).

    Returns:
        The ordered list of HTML message strings to send with ``parse_mode=HTML``
        (at least one — a header-only message when the body is empty).
    """
    name = persona.display_name
    header = f"<b>{escape_html(name)}</b>"
    # The header occupies ``utf16(name) + 1`` visible units (the name + the newline
    # before the body) — reserve that from the first part's budget.
    reserve = utf16_length(name) + 1
    first_budget = max(1, budget - reserve)

    body_chunks = split_text(text, budget=budget, first_budget=first_budget)
    if not body_chunks:
        return [header]
    messages: list[str] = []
    for index, chunk in enumerate(body_chunks):
        escaped = escape_html(chunk)
        messages.append(f"{header}\n{escaped}" if index == 0 else escaped)
    return messages

"""Discord outbound rendering (Spec C3) — Markdown bold tag + code-point split.

Proves: the ``**Name**`` header lands on the first part only; the body is sent as-is
(no HTML-style escaping — Discord renders Markdown); the split honours Discord's
2000-code-point budget (markup counts) via the shared splitter.
"""

from __future__ import annotations

from persona.schema.origination import PersonaIdentityTag
from persona_connectors.discord.render import render_outbound
from persona_connectors.domain.render import codepoint_measure

_PERSONA = PersonaIdentityTag(persona_id="p1", display_name="Astrid", visual_ref=None)


def test_short_reply_has_bold_header_then_body() -> None:
    parts = render_outbound(_PERSONA, "hello there", budget=100)
    assert parts == ["**Astrid**\nhello there"]


def test_body_is_not_escaped() -> None:
    """Discord renders Markdown — the body passes through verbatim (no HTML escaping)."""
    parts = render_outbound(_PERSONA, "1 < 2 & 3 > 0", budget=100)
    assert parts == ["**Astrid**\n1 < 2 & 3 > 0"]


def test_header_on_first_part_only() -> None:
    body = "alpha beta gamma delta epsilon zeta eta theta"
    parts = render_outbound(_PERSONA, body, budget=20)
    assert len(parts) > 1
    assert parts[0].startswith("**Astrid**\n")
    for continuation in parts[1:]:
        assert "**Astrid**" not in continuation


def test_every_part_within_the_codepoint_budget() -> None:
    body = "word " * 200  # 1000 chars → must split under a small budget
    parts = render_outbound(_PERSONA, body, budget=50)
    assert len(parts) > 1
    for part in parts:
        assert codepoint_measure(part) <= 50


def test_empty_body_is_header_only() -> None:
    assert render_outbound(_PERSONA, "", budget=100) == ["**Astrid**"]

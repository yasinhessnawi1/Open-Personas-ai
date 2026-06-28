"""Slack outbound rendering (Spec C3) — mrkdwn single-asterisk bold + code-point split.

Proves: the ``*Name*`` header (SINGLE asterisk — the naive-port bug guard) on the first
part only; the body is mrkdwn-escaped (``& < >``); the split honours the readable budget.
"""

from __future__ import annotations

from persona.schema.origination import PersonaIdentityTag
from persona_connectors.domain.render import codepoint_measure
from persona_connectors.slack.render import escape_mrkdwn, render_outbound

_PERSONA = PersonaIdentityTag(persona_id="p1", display_name="Astrid", visual_ref=None)


def test_short_reply_has_single_asterisk_bold_header() -> None:
    parts = render_outbound(_PERSONA, "hello there", budget=100)
    assert parts == ["*Astrid*\nhello there"]  # SINGLE asterisk (not **)


def test_body_and_name_are_mrkdwn_escaped() -> None:
    persona = PersonaIdentityTag(persona_id="p", display_name="A<b>", visual_ref=None)
    parts = render_outbound(persona, "1 < 2 & 3 > 0", budget=100)
    assert parts == ["*A&lt;b&gt;*\n1 &lt; 2 &amp; 3 &gt; 0"]


def test_escape_mrkdwn_orders_ampersand_first() -> None:
    assert escape_mrkdwn("<a & b>") == "&lt;a &amp; b&gt;"


def test_header_on_first_part_only() -> None:
    body = "alpha beta gamma delta epsilon zeta eta theta"
    parts = render_outbound(_PERSONA, body, budget=20)
    assert len(parts) > 1
    assert parts[0].startswith("*Astrid*\n")
    for continuation in parts[1:]:
        assert "*Astrid*" not in continuation


def test_every_part_within_budget() -> None:
    parts = render_outbound(_PERSONA, "word " * 200, budget=50)
    assert len(parts) > 1
    for part in parts:
        assert codepoint_measure(part) <= 50


def test_empty_body_is_header_only() -> None:
    assert render_outbound(_PERSONA, "", budget=100) == ["*Astrid*"]

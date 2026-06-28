"""Shared splitter + length measures (Spec C3 amendment #1, D-C3-X-splitter).

The platform-agnostic split lifted from the Telegram adapter, now parameterised by
a length ``measure``: paragraph → line → sentence → word, never mid-word, never
mid-surrogate, hard-wrap last resort, optional smaller first_budget. Telegram
counts UTF-16 units; Discord/Slack count code points — both exercised here.
"""

from __future__ import annotations

import pytest
from persona_connectors.domain.render import (
    codepoint_measure,
    split_text,
    utf16_measure,
)

# --- measures ---


def test_utf16_measure_counts_astral_as_two() -> None:
    """An emoji is one code point but two UTF-16 units (Telegram's unit)."""
    assert utf16_measure("ab") == 2
    assert utf16_measure("😀") == 2  # U+1F600 — a surrogate pair
    assert utf16_measure("a😀b") == 4


def test_codepoint_measure_counts_astral_as_one() -> None:
    """An emoji is a single code point (Discord/Slack's unit)."""
    assert codepoint_measure("ab") == 2
    assert codepoint_measure("😀") == 1
    assert codepoint_measure("a😀b") == 3


# --- split_text: boundaries (default code-point measure) ---


def test_short_text_is_one_chunk() -> None:
    assert split_text("hello world", budget=100) == ["hello world"]


def test_split_prefers_paragraph_then_line_then_sentence_then_word() -> None:
    """Greedy split prefers the largest chunk ending on the strongest boundary."""
    assert split_text("alpha beta\n\ngamma delta", budget=12) == ["alpha beta", "gamma delta"]


def test_split_breaks_on_sentence_boundary() -> None:
    """A sentence boundary is preferred over a mere word break when both fit."""
    assert split_text("One two. Three four.", budget=12) == ["One two.", "Three four."]


def test_split_never_breaks_mid_word() -> None:
    parts = split_text("alpha beta gamma delta", budget=12)
    for part in parts:
        for word in part.split():
            assert word in {"alpha", "beta", "gamma", "delta"}
    assert "".join(p.replace(" ", "") for p in parts) == "alphabetagammadelta"


def test_split_hard_wraps_an_oversized_token() -> None:
    """A single word longer than budget is hard-wrapped (last resort), losing nothing."""
    parts = split_text("supercalifragilistic", budget=5)
    assert "".join(parts) == "supercalifragilistic"
    assert all(codepoint_measure(p) <= 5 for p in parts)


def test_split_first_budget_is_smaller() -> None:
    """The first chunk honours a reduced first_budget (header reserve)."""
    parts = split_text("aaaa bbbb cccc", budget=9, first_budget=4)
    assert codepoint_measure(parts[0]) <= 4


def test_split_empty_text_is_empty_list() -> None:
    assert split_text("", budget=100) == []
    assert split_text("   ", budget=100) == []


def test_split_rejects_nonpositive_budget() -> None:
    with pytest.raises(ValueError, match="budget"):
        split_text("x", budget=0)


def test_split_rejects_nonpositive_first_budget() -> None:
    with pytest.raises(ValueError, match="first_budget"):
        split_text("x", budget=10, first_budget=0)


# --- split_text: the measure is honoured ---


def test_split_respects_utf16_budget() -> None:
    """With the UTF-16 measure every chunk is within budget (emoji counts as 2)."""
    text = "😀 😀 😀 😀 😀"
    parts = split_text(text, budget=5, measure=utf16_measure)
    assert parts
    for part in parts:
        assert utf16_measure(part) <= 5


def test_split_does_not_tear_a_surrogate_pair() -> None:
    """A hard-wrap of emoji-only text never splits mid-surrogate (chunks stay valid)."""
    text = "😀😀😀😀"  # no boundaries → hard-wrapped; 8 UTF-16 units total
    parts = split_text(text, budget=3, measure=utf16_measure)  # one emoji (2) per chunk
    assert "".join(parts) == text
    for part in parts:
        part.encode("utf-16")  # raises on a lone surrogate


def test_codepoint_measure_packs_more_emoji_than_utf16() -> None:
    """The SAME emoji text + budget yields fewer chunks under the code-point measure.

    Proves the measure actually drives the budget: under code points an emoji is 1
    unit, so a budget of 3 fits more of them per chunk than UTF-16 (2 units each).
    """
    text = "😀😀😀😀"
    codepoint_parts = split_text(text, budget=3, measure=codepoint_measure)
    utf16_parts = split_text(text, budget=3, measure=utf16_measure)
    assert "".join(codepoint_parts) == text
    assert len(codepoint_parts) < len(utf16_parts)

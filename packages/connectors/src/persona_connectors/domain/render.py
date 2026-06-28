"""Shared outbound text splitting + length measures (Spec C3 amendment #1, D-C3-X-splitter).

The boundary-aware message splitter — lifted from the C2 Telegram adapter
(``telegram/render.py``; D-C2-3 named it "reusable C3/C4" but it was hard-coded to
UTF-16) into the framework's owned surface so every text adapter (Telegram /
Discord / Slack / …) shares ONE split algorithm and supplies only its platform's
length **measure**:

- :func:`utf16_measure` — Telegram counts in UTF-16 code units (an astral char = 2).
- :func:`codepoint_measure` — Discord / Slack count Unicode code points (``len``).

Each platform's *rendering* (wrapping the persona name tag in HTML / Markdown /
mrkdwn + the per-platform escaping) stays **adapter-owned** (C1-D-6: core never
carries platform markup). This module owns only the platform-agnostic split:
paragraph → line → sentence → word, **never mid-word**, **never mid-surrogate**, a
last-resort hard-wrap, and an optional smaller first-chunk budget (the name-header
reserve). Splitting the **plaintext** (then the adapter wraps each part) is what
keeps a markup tag from tearing across a boundary.

Owned surface — api-free; stdlib only.
"""

from __future__ import annotations

from collections.abc import Callable

__all__ = [
    "LengthMeasure",
    "codepoint_measure",
    "split_text",
    "utf16_measure",
]

# A function measuring a string's length in a platform's counting unit.
LengthMeasure = Callable[[str], int]


def utf16_measure(text: str) -> int:
    """Length in UTF-16 code units — Telegram's unit (an astral char counts as 2).

    A code point above U+FFFF (emoji, some CJK) occupies two UTF-16 units, so this
    is ``>= len(text)``.
    """
    return sum(2 if ord(ch) > 0xFFFF else 1 for ch in text)


def codepoint_measure(text: str) -> int:
    """Length in Unicode code points — Discord / Slack's unit (plain ``len``)."""
    return len(text)


def _max_prefix_len(text: str, budget: int, measure: LengthMeasure) -> int:
    """Largest code-point index ``i`` with ``measure(text[:i]) <= budget``.

    Iterating by code point means a surrogate pair is never split (an astral char
    is one element contributing its full unit-width atomically).
    """
    total = 0
    for index, ch in enumerate(text):
        units = measure(ch)
        if total + units > budget:
            return index
        total += units
    return len(text)


def _find_break(window: str) -> int:
    """The best natural break index within ``window`` (the rightmost boundary).

    Preference: paragraph (``\\n\\n``) → line (``\\n``) → sentence
    (``. `` / ``! `` / ``? ``) → word (whitespace). Returns the index to cut at
    (everything before it is one chunk), or ``-1`` when ``window`` has no boundary
    (the caller hard-wraps).
    """
    paragraph = window.rfind("\n\n")
    if paragraph != -1:
        return paragraph + 2
    line = window.rfind("\n")
    if line != -1:
        return line + 1
    sentence = max(window.rfind(". "), window.rfind("! "), window.rfind("? "))
    if sentence != -1:
        return sentence + 2  # cut after the terminator + its space
    word = max(window.rfind(" "), window.rfind("\t"))
    if word != -1:
        return word + 1
    return -1


def split_text(
    text: str,
    *,
    budget: int,
    first_budget: int | None = None,
    measure: LengthMeasure = codepoint_measure,
) -> list[str]:
    """Split ``text`` into chunks within ``budget`` (in ``measure`` units), on boundaries.

    Args:
        text: The plaintext to split (markup-free — render/escape happens after, in
            the adapter, so a markup tag never tears across a boundary).
        budget: Max units per chunk, counted by ``measure``.
        first_budget: A smaller budget for the FIRST chunk (it reserves room for a
            name header); ``None`` → use ``budget`` for every chunk.
        measure: The platform's length measure (``codepoint_measure`` default;
            ``utf16_measure`` for Telegram). One char's measure is its unit-width.

    Returns:
        Non-empty, whitespace-trimmed chunks, each within its budget, in order. A
        chunk breaks on a paragraph/line/sentence/word boundary where one exists
        within budget; a single over-budget token is hard-wrapped as a last resort.

    Raises:
        ValueError: ``budget`` (or a provided ``first_budget``) is below 1.
    """
    if budget < 1:
        raise ValueError("budget must be >= 1")
    if first_budget is not None and first_budget < 1:
        raise ValueError("first_budget must be >= 1")

    chunks: list[str] = []
    remaining = text
    while remaining:
        cap = first_budget if (not chunks and first_budget is not None) else budget
        if measure(remaining) <= cap:
            chunk, remaining = remaining, ""
        else:
            max_index = _max_prefix_len(remaining, cap, measure) or 1  # guarantee progress
            window = remaining[:max_index]
            cut = _find_break(window)
            if cut <= 0:
                cut = max_index  # no boundary in budget → hard-wrap
            chunk, remaining = remaining[:cut], remaining[cut:]
        trimmed = chunk.strip()
        if trimmed:
            chunks.append(trimmed)
    return chunks

"""``md`` format handler — new common format (D-24-1, spec §2.1)."""

from __future__ import annotations

from persona.skills.document_generation.protocol import FormatHandler

#: Markdown ``.md`` — pure-text, no rendering library, no supplements.
MARKDOWN = FormatHandler(
    format_key="md",
    output_extension=".md",
    library="stdlib",
    supplement_topics=(),
)

__all__ = ["MARKDOWN"]

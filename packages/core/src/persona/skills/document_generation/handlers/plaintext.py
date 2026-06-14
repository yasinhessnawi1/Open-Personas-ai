"""``txt`` format handler — new common format (D-24-1, spec §2.1)."""

from __future__ import annotations

from persona.skills.document_generation.protocol import FormatHandler

#: Plain text ``.txt`` — pure-text, no rendering library, no supplements.
PLAINTEXT = FormatHandler(
    format_key="txt",
    output_extension=".txt",
    library="stdlib",
    supplement_topics=(),
)

__all__ = ["PLAINTEXT"]

"""``docx`` format handler — was ``builtin/docx_generation/`` (D-24-1)."""

from __future__ import annotations

from persona.skills.document_generation.protocol import FormatHandler

#: Word ``.docx`` via ``python-docx`` in the sandbox.
DOCX = FormatHandler(
    format_key="docx",
    output_extension=".docx",
    library="python-docx==1.1.2",
    supplement_topics=("tables", "styles", "images", "toc"),
)

__all__ = ["DOCX"]

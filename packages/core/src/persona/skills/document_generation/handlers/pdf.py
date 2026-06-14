"""``pdf`` format handler — was ``builtin/pdf_generation/`` (D-24-1)."""

from __future__ import annotations

from persona.skills.document_generation.protocol import FormatHandler

#: PDF report via ``reportlab`` (flowable model) in the sandbox.
PDF = FormatHandler(
    format_key="pdf",
    output_extension=".pdf",
    library="reportlab==4.2.5",
    supplement_topics=("flowables", "pagination", "images"),
)

__all__ = ["PDF"]

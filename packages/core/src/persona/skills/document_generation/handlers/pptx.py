"""``pptx`` format handler — was ``builtin/pptx_generation/`` (D-24-1)."""

from __future__ import annotations

from persona.skills.document_generation.protocol import FormatHandler

#: PowerPoint ``.pptx`` via ``python-pptx`` in the sandbox.
PPTX = FormatHandler(
    format_key="pptx",
    output_extension=".pptx",
    library="python-pptx==1.0.2",
    supplement_topics=("layouts", "charts", "theme"),
)

__all__ = ["PPTX"]

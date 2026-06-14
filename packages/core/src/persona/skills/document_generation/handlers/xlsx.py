"""``xlsx`` format handler — was ``builtin/xlsx_generation/`` (D-24-1)."""

from __future__ import annotations

from persona.skills.document_generation.protocol import FormatHandler

#: Excel ``.xlsx`` via ``openpyxl`` in the sandbox.
XLSX = FormatHandler(
    format_key="xlsx",
    output_extension=".xlsx",
    library="openpyxl==3.1.5",
    supplement_topics=("formulas", "formatting", "charts"),
)

__all__ = ["XLSX"]

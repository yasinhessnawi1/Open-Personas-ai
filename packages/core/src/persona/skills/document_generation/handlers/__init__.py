"""Per-format :class:`FormatHandler` descriptors (D-24-1, surface #3).

One module per supported document format. Each exposes a module-level frozen
``FormatHandler`` constant migrated from the corresponding pre-Spec-24 builtin
skill (``docx_generation`` → ``docx``, etc.). The registry aggregates them.
Adding a format = add a module here + one ``FORMAT_HANDLERS`` entry.
"""

from __future__ import annotations

from persona.skills.document_generation.handlers.docx import DOCX
from persona.skills.document_generation.handlers.markdown import MARKDOWN
from persona.skills.document_generation.handlers.pdf import PDF
from persona.skills.document_generation.handlers.plaintext import PLAINTEXT
from persona.skills.document_generation.handlers.pptx import PPTX
from persona.skills.document_generation.handlers.xlsx import XLSX

__all__ = ["DOCX", "MARKDOWN", "PDF", "PLAINTEXT", "PPTX", "XLSX"]

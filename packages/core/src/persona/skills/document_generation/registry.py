"""Format + template registry for ``document_generation`` (D-24-1; surfaces #1/#4).

Single source of truth for the supported document formats and bundled
templates. Adding a format = add ``handlers/<format>.py`` + a ``FORMAT_HANDLERS``
entry (no new top-level skill directory — that is the whole point of D-24-1).
Adding a template = drop ``templates/<id>.md`` in the builtin skill dir + a
``TEMPLATES`` entry.

Curated 6-format scope per D-24-1: ``docx`` / ``pdf`` / ``pptx`` / ``xlsx`` /
``md`` / ``txt``. Resolution is a dict-membership lookup over the registry — a
closed map, never a path join on caller-supplied input (path-traversal-safe per
research §2.3).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.errors import UnknownDocumentFormatError, UnknownDocumentTemplateError
from persona.skills.document_generation.handlers import (
    DOCX,
    MARKDOWN,
    PDF,
    PLAINTEXT,
    PPTX,
    XLSX,
)

if TYPE_CHECKING:
    from persona.skills.document_generation.protocol import DocumentHandler

__all__ = [
    "FORMAT_HANDLERS",
    "TEMPLATES",
    "resolve_format",
    "resolve_template",
    "supported_formats",
    "supported_templates",
]

#: ``format`` parameter value → handler descriptor. Curated 6 (D-24-1).
FORMAT_HANDLERS: dict[str, DocumentHandler] = {
    handler.format_key: handler for handler in (DOCX, PDF, PPTX, XLSX, MARKDOWN, PLAINTEXT)
}

#: ``template`` id → bundled Markdown filename under
#: ``builtin/document_generation/templates/`` (D-24-2 placeholder templates).
TEMPLATES: dict[str, str] = {
    "memo": "memo.md",
    "report": "report.md",
    "business_letter": "business_letter.md",
    "research_paper": "research_paper.md",
}


def supported_formats() -> tuple[str, ...]:
    """Return the registered format keys, sorted (stable for the index/enum)."""
    return tuple(sorted(FORMAT_HANDLERS))


def supported_templates() -> tuple[str, ...]:
    """Return the registered template ids, sorted."""
    return tuple(sorted(TEMPLATES))


def resolve_format(format_key: str) -> DocumentHandler:
    """Return the handler for ``format_key``.

    Args:
        format_key: The requested format (e.g. ``"docx"``).

    Returns:
        The matching :class:`DocumentHandler` descriptor.

    Raises:
        UnknownDocumentFormatError: ``format_key`` has no registered handler;
            ``context`` names the rejected format + the available set.
    """
    try:
        return FORMAT_HANDLERS[format_key]
    except KeyError:
        raise UnknownDocumentFormatError(
            "unknown document format",
            context={
                "format": format_key,
                "available": ", ".join(supported_formats()),
            },
        ) from None


def resolve_template(template_id: str) -> str:
    """Return the bundled template filename for ``template_id``.

    Args:
        template_id: The requested template (e.g. ``"business_letter"``).

    Returns:
        The template's filename under ``builtin/document_generation/templates/``.

    Raises:
        UnknownDocumentTemplateError: ``template_id`` is not registered;
            ``context`` names the rejected template + the available set.
    """
    try:
        return TEMPLATES[template_id]
    except KeyError:
        raise UnknownDocumentTemplateError(
            "unknown document template",
            context={
                "template": template_id,
                "available": ", ".join(supported_templates()),
            },
        ) from None

"""Document-generation dispatch code (Spec 24, D-24-1 — Reading B).

This package holds the **code** that drives the unified ``document_generation``
skill: the :class:`DocumentHandler` Protocol, the concrete per-format
descriptors, and the format/template :mod:`registry`. The skill **data**
(``SKILL.md`` + ``supplements/`` + ``templates/``) lives separately under
``persona.skills.builtin.document_generation`` so the scanner sees one skill
directory while dispatch logic stays importable and ``mypy --strict`` clean.

Reading B (D-24-1): a "handler" is an instruction-dispatch *descriptor*, not an
in-process renderer. The model writes code that runs in the ``code_execution``
sandbox; persona-core takes **zero** rendering dependencies. New format =
``handlers/<format>.py`` + one ``FORMAT_HANDLERS`` entry; no new top-level
skill directory.
"""

from __future__ import annotations

from persona.skills.document_generation.protocol import DocumentHandler, FormatHandler
from persona.skills.document_generation.registry import (
    FORMAT_HANDLERS,
    TEMPLATES,
    resolve_format,
    resolve_template,
    supported_formats,
    supported_templates,
)

__all__ = [
    "FORMAT_HANDLERS",
    "TEMPLATES",
    "DocumentHandler",
    "FormatHandler",
    "resolve_format",
    "resolve_template",
    "supported_formats",
    "supported_templates",
]

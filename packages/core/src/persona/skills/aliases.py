"""Backward-compat aliases for the 5 deleted document-format skills (D-24-3, D-24-9).

Spec 24 deletes ``docx_generation`` / ``pdf_generation`` / ``pptx_generation`` /
``xlsx_generation`` / ``document_drafting`` and folds them into the single
``document_generation`` skill (D-24-1). Existing persona YAMLs in the wild still
declare the old names; the scanner rewrites them here so those personas keep
working **without modification** (acceptance #2/#3). The alias shim is what makes
the deletion safe — without it, Spec 24 would be a breaking change.

Deprecation timeline (D-24-3): **v0.2** resolves silently-but-logged at INFO;
**v0.3** opens the deprecation window with a WARN; **v0.4** removes the aliases.
"""

from __future__ import annotations

from persona.logging import get_logger

__all__ = ["SKILL_ALIASES", "resolve_skill_aliases"]

_logger = get_logger("skills.aliases")

#: Deprecated skill name → ``(replacement_skill, pre-filled_format | None)``.
#: ``document_drafting`` carries no format (it was the prose/template path);
#: the four ``*_generation`` skills each pin their format.
SKILL_ALIASES: dict[str, tuple[str, str | None]] = {
    "docx_generation": ("document_generation", "docx"),
    "pdf_generation": ("document_generation", "pdf"),
    "pptx_generation": ("document_generation", "pptx"),
    "xlsx_generation": ("document_generation", "xlsx"),
    "document_drafting": ("document_generation", None),
}


def resolve_skill_aliases(declared: list[str]) -> list[str]:
    """Rewrite deprecated skill names to their replacement; dedup; INFO-log.

    Declared order is preserved; the first occurrence of each resolved name
    wins and later duplicates collapse (e.g. a persona declaring both
    ``docx_generation`` and ``pdf_generation`` ends up with a single
    ``document_generation`` entry — the unified skill picks the format per
    call). One INFO log is emitted per alias resolution (D-24-3 v0.2 stage).

    Args:
        declared: The persona's raw ``skills: [...]`` list.

    Returns:
        The de-aliased, de-duplicated skill-name list, declared-order-preserving.
    """
    out: list[str] = []
    seen: set[str] = set()
    for name in declared:
        entry = SKILL_ALIASES.get(name)
        if entry is not None:
            target, fmt = entry
            _logger.info(
                "resolved deprecated skill alias to document_generation",
                alias=name,
                target=target,
                format=fmt or "(none)",
            )
            resolved = target
        else:
            resolved = name
        if resolved not in seen:
            seen.add(resolved)
            out.append(resolved)
    return out

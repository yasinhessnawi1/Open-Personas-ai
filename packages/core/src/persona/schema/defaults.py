"""The default persona capability floor and its idempotent re-assert.

Single source of truth for the baseline tools + skills every persona must carry,
regardless of how it was authored. A persona created without these can't read an
uploaded file, run code, search the web, or generate a document — so it answers
from imagination and hallucinates. The authoring prompt *suggests* a sensible
capability set, but instruction-following is not a guarantee — and direct-create
(a structured YAML posted without any model in the loop) is a first-class
creation path. :func:`ensure_default_capabilities` is the enforcement *floor*: it
guarantees the baseline on any persona however it was authored (direct-create,
drafter, CLI, prebuilt starter), so the invariant never rests on a model
following instructions or a client remembering to inject it.

Mirrors the mandatory safety-constraint pattern in :mod:`persona.schema.safety`:
both are append-only, idempotent floors that return the *same* object when
nothing is missing (frozen-model copy only on change).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from persona.schema.persona import Persona

__all__ = ["DEFAULT_SKILLS", "DEFAULT_TOOLS", "ensure_default_capabilities"]

#: The baseline tools every persona must carry. ``file_read`` lets it read
#: uploaded files, ``code_execution`` lets it run code, ``web_search`` lets it
#: look facts up — the trio that keeps a persona grounded instead of guessing.
#: All are valid catalog names.
DEFAULT_TOOLS: tuple[str, ...] = ("file_read", "code_execution", "web_search")

#: The baseline skills every persona must carry. ``document_generation`` is a
#: real built-in skill that produces documents; it requires ``code_execution``
#: (in :data:`DEFAULT_TOOLS`), so the two belong together.
DEFAULT_SKILLS: tuple[str, ...] = ("document_generation",)


def ensure_default_capabilities(persona: Persona) -> Persona:
    """Return a persona guaranteed to carry the default tools and skills.

    Idempotent: if every name in :data:`DEFAULT_TOOLS` is already in
    ``persona.tools`` and every name in :data:`DEFAULT_SKILLS` is already in
    ``persona.skills``, the persona is returned unchanged (same object).
    Otherwise the missing defaults are appended *after* the persona's existing
    entries — existing order is preserved and never reordered, and the appended
    defaults follow :data:`DEFAULT_TOOLS` / :data:`DEFAULT_SKILLS` order. No
    duplicates are ever introduced.

    Args:
        persona: The persona to guard.

    Returns:
        The same persona when no default is missing, otherwise a copy whose
        ``tools`` / ``skills`` carry every default (existing entries first).
    """
    missing_tools = [tool for tool in DEFAULT_TOOLS if tool not in persona.tools]
    missing_skills = [skill for skill in DEFAULT_SKILLS if skill not in persona.skills]
    if not missing_tools and not missing_skills:
        return persona
    return persona.model_copy(
        update={
            "tools": [*persona.tools, *missing_tools],
            "skills": [*persona.skills, *missing_skills],
        }
    )

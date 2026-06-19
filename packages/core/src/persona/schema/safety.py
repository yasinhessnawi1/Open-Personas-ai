"""The mandatory persona safety constraint and its idempotent re-assert.

Single source of truth for the verbatim safety constraint every persona must
carry (Spec 36, D-36-safety-constant / D-36-safety-server). The drafter's
authoring prompt *instructs* the model to emit it, but instruction-following is
not a guarantee — and Spec 36 makes direct-create (a structured YAML posted
without any model in the loop) the primary creation path. :func:`ensure_safety_constraint`
is the enforcement *floor*: it guarantees the constraint on any persona however
it was authored (direct-create, drafter, CLI), so the invariant never rests on a
model following instructions or a client remembering to inject it.

The web layer mirrors :data:`SAFETY_CONSTRAINT` as a single exported constant for
its client-side guard + pinned UI chip; a cross-language test asserts the two
literals match byte-for-byte (the drift guard). This module is the Python source
of truth.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from persona.schema.persona import Persona

__all__ = ["SAFETY_CONSTRAINT", "ensure_safety_constraint"]

#: The verbatim safety constraint, in English, that every persona must carry as
#: a hard constraint — even when the persona speaks another language. Mirrored
#: in the authoring prompt (:mod:`persona_api.services.authoring_prompt`) and the
#: web dataset/guard; those references import or drift-test against this value.
SAFETY_CONSTRAINT = "Do not fabricate information; say when you don't know."


def ensure_safety_constraint(persona: Persona) -> Persona:
    """Return a persona guaranteed to carry the verbatim safety constraint.

    Idempotent: if :data:`SAFETY_CONSTRAINT` is already present anywhere in
    ``identity.constraints`` the persona is returned unchanged (same object);
    otherwise the constraint is prepended as the first constraint. Existing
    constraints are never removed or reordered.

    Args:
        persona: The persona to guard.

    Returns:
        The same persona when the constraint is already present, otherwise a
        copy whose ``identity.constraints`` begins with the safety constraint.
    """
    if SAFETY_CONSTRAINT in persona.identity.constraints:
        return persona
    guarded_identity = persona.identity.model_copy(
        update={"constraints": [SAFETY_CONSTRAINT, *persona.identity.constraints]}
    )
    return persona.model_copy(update={"identity": guarded_identity})

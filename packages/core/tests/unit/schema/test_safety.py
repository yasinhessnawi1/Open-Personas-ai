"""Unit tests for the mandatory safety constraint + idempotent re-assert.

Spec 36 (D-36-safety-constant / D-36-safety-server). The constant is the Python
source of truth; ``ensure_safety_constraint`` is the enforcement floor that does
not rest on a model or a client remembering to inject it.
"""

from __future__ import annotations

from persona.schema import SAFETY_CONSTRAINT, ensure_safety_constraint
from persona.schema.persona import Persona, PersonaIdentity


def _persona(constraints: list[str]) -> Persona:
    return Persona(
        identity=PersonaIdentity(
            name="Test",
            role="Tester",
            background="A persona used in tests.",
            constraints=constraints,
        )
    )


def test_constant_is_the_verbatim_safety_sentence() -> None:
    assert SAFETY_CONSTRAINT == "Do not fabricate information; say when you don't know."


def test_prepends_when_absent() -> None:
    guarded = ensure_safety_constraint(_persona(["Cite a source for every claim."]))
    assert guarded.identity.constraints == [
        SAFETY_CONSTRAINT,
        "Cite a source for every claim.",
    ]


def test_prepends_onto_empty_constraints() -> None:
    guarded = ensure_safety_constraint(_persona([]))
    assert guarded.identity.constraints == [SAFETY_CONSTRAINT]


def test_idempotent_when_present_returns_same_object() -> None:
    persona = _persona([SAFETY_CONSTRAINT, "Cite a source."])
    # No copy, no duplicate — present means untouched.
    assert ensure_safety_constraint(persona) is persona


def test_does_not_reorder_when_present_but_not_first() -> None:
    persona = _persona(["Cite a source.", SAFETY_CONSTRAINT])
    guarded = ensure_safety_constraint(persona)
    assert guarded is persona
    assert guarded.identity.constraints == ["Cite a source.", SAFETY_CONSTRAINT]


def test_never_duplicates_the_constraint() -> None:
    guarded = ensure_safety_constraint(_persona([SAFETY_CONSTRAINT]))
    assert guarded.identity.constraints.count(SAFETY_CONSTRAINT) == 1


def test_preserves_other_identity_fields() -> None:
    guarded = ensure_safety_constraint(_persona(["Keep confidences."]))
    assert guarded.identity.name == "Test"
    assert guarded.identity.role == "Tester"
    assert guarded.identity.background == "A persona used in tests."

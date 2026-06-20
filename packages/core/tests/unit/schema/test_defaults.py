"""Unit tests for the default capability floor + idempotent re-assert.

The constants are the Python source of truth; ``ensure_default_capabilities`` is
the enforcement floor that guarantees every persona carries the baseline tools +
skills regardless of how it was authored — it does not rest on a model or a
client remembering to inject them.
"""

from __future__ import annotations

from persona.schema import DEFAULT_SKILLS, DEFAULT_TOOLS, ensure_default_capabilities
from persona.schema.persona import Persona, PersonaIdentity


def _persona(*, tools: list[str], skills: list[str]) -> Persona:
    return Persona(
        identity=PersonaIdentity(
            name="Test",
            role="Tester",
            background="A persona used in tests.",
        ),
        tools=tools,
        skills=skills,
    )


def test_constants_have_the_exact_expected_values() -> None:
    assert DEFAULT_TOOLS == ("file_read", "code_execution", "web_search")
    assert DEFAULT_SKILLS == ("document_generation",)


def test_empty_persona_gets_all_defaults() -> None:
    guarded = ensure_default_capabilities(_persona(tools=[], skills=[]))
    assert guarded.tools == ["file_read", "code_execution", "web_search"]
    assert guarded.skills == ["document_generation"]


def test_idempotent_when_all_present_returns_same_object() -> None:
    persona = _persona(tools=list(DEFAULT_TOOLS), skills=list(DEFAULT_SKILLS))
    # All present means untouched — no copy, no duplicate.
    result = ensure_default_capabilities(persona)
    assert result is persona


def test_partial_adds_only_missing_no_duplicates_existing_first() -> None:
    persona = _persona(
        tools=["web_search", "calculator"],
        skills=[],
    )
    guarded = ensure_default_capabilities(persona)
    # Existing entries kept first + in order; missing defaults appended after in
    # DEFAULT_TOOLS order; no duplicate of the already-present web_search.
    assert guarded.tools == ["web_search", "calculator", "file_read", "code_execution"]
    assert guarded.tools.count("web_search") == 1
    assert guarded.skills == ["document_generation"]


def test_partial_skills_only_preserves_existing_and_appends_default() -> None:
    persona = _persona(tools=list(DEFAULT_TOOLS), skills=["data_analysis"])
    guarded = ensure_default_capabilities(persona)
    # tools already complete; only the missing skill is appended after existing.
    assert guarded.tools == list(DEFAULT_TOOLS)
    assert guarded.skills == ["data_analysis", "document_generation"]


def test_preserves_other_persona_fields() -> None:
    guarded = ensure_default_capabilities(_persona(tools=[], skills=[]))
    assert guarded.identity.name == "Test"
    assert guarded.identity.role == "Tester"
    assert guarded.identity.background == "A persona used in tests."


def test_run_twice_is_stable() -> None:
    once = ensure_default_capabilities(_persona(tools=[], skills=[]))
    twice = ensure_default_capabilities(once)
    # Second pass finds nothing missing → same object back.
    assert twice is once
    assert twice.tools.count("file_read") == 1
    assert twice.skills.count("document_generation") == 1

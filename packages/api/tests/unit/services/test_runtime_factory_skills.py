"""Unit regression test for the runtime-factory skill-scanner wiring.

Regression guard for the bug where ``RuntimeFactory._scan_skills`` was
constructing ``SkillScanner(skill_paths=[])`` with an empty path list,
so every persona-declared skill logged ``"declared skill not found"``
at every chat turn and the loop never injected any skill content.

The fix wires the shared :data:`persona.skills.BUILTIN_ROOT` constant
into both :class:`SkillScanner` instantiations (this service + the
catalog service) so they resolve declared skills against the same
on-disk directory. This test asserts that:

1. ``BUILTIN_ROOT`` is exported from ``persona.skills``.
2. A :class:`SkillScanner` constructed with ``skill_paths=[BUILTIN_ROOT]``
   resolves the bundled skill names (``web_research``, ``data_analysis``,
   ``document_generation``) to non-``None`` specs, AND that the Spec 24
   deprecated names (``document_drafting`` / ``docx_generation`` /
   ``pptx_generation`` / ``xlsx_generation`` / ``pdf_generation``) keep
   resolving via the alias shim to ``document_generation`` (D-24-3 /
   D-24-9 — coverage relocated here from the deleted Spec 16 packs).
3. The catalog service and the runtime factory import ``BUILTIN_ROOT``
   from the same source (single source of truth — no parallel
   definitions that could drift).

A future refactor that resets ``runtime_factory`` to ``skill_paths=[]``
or otherwise breaks the wiring fails this test loud.
"""

from __future__ import annotations

import pytest
from persona.skills import BUILTIN_ROOT, SkillScanner
from persona.skills.document_generation import supported_formats


def test_builtin_root_points_at_a_real_directory_with_skill_packs() -> None:
    """``BUILTIN_ROOT`` is a real on-disk directory containing skill packs."""
    assert BUILTIN_ROOT.exists(), f"BUILTIN_ROOT does not exist: {BUILTIN_ROOT}"
    assert BUILTIN_ROOT.is_dir(), f"BUILTIN_ROOT is not a directory: {BUILTIN_ROOT}"
    # Each bundled skill ships as a sub-directory with a SKILL.md. The 5
    # document-format packs were folded into document_generation (D-24-1).
    bundled = {"web_research", "data_analysis", "document_generation"}
    found = {p.name for p in BUILTIN_ROOT.iterdir() if p.is_dir()}
    missing = bundled - found
    assert not missing, f"bundled skills missing from BUILTIN_ROOT: {missing}"


def test_skill_scanner_with_builtin_root_resolves_bundled_skills() -> None:
    """``SkillScanner(skill_paths=[BUILTIN_ROOT])`` finds the bundled skills.

    This is the core regression guard: the runtime factory's
    ``_scan_skills`` constructs a scanner with this exact ``skill_paths``;
    if any persona's ``skills: [...]`` declaration includes a bundled
    skill, the scanner MUST return a non-``None`` spec. Empty
    ``skill_paths`` (the prior bug) returns ``None`` for every declared
    skill and logs ``"declared skill not found"``.

    ``document_drafting`` is a Spec-24-deprecated name; it resolves via
    the alias shim to ``document_generation`` (the coverage relocation —
    old persona YAMLs keep working).
    """
    scanner = SkillScanner(skill_paths=[BUILTIN_ROOT])
    scanned = scanner.scan(declared_skills=["web_research", "document_drafting"])
    assert len(scanned) == 2, (
        f"expected both bundled skills to resolve; got {[s.name for s in scanned]}"
    )
    names = {s.name for s in scanned}
    # document_drafting → document_generation via the alias (D-24-9).
    assert names == {"web_research", "document_generation"}


def test_skill_scanner_with_empty_paths_finds_nothing_regression_baseline() -> None:
    """Empty ``skill_paths`` resolves nothing — the prior-bug baseline.

    Documents the *negative* invariant: if a future change reverts the
    runtime factory wiring to ``skill_paths=[]`` (the bug), the scanner
    silently returns an empty list. This test exists as the explicit
    record of why the wiring matters; the positive test above is the
    actual guard.
    """
    scanner = SkillScanner(skill_paths=[])
    scanned = scanner.scan(declared_skills=["web_research", "document_drafting"])
    assert scanned == [], "empty skill_paths must resolve nothing"


def test_runtime_factory_and_catalog_share_builtin_root_source() -> None:
    """Both services import ``BUILTIN_ROOT`` from the same module.

    Prevents the failure mode where each service defines its own
    ``_BUILTIN_SKILLS_DIR`` constant and the two drift over time.
    Asserts the module-level identity of the imported constant.
    """
    from persona.skills import BUILTIN_ROOT as CORE_BUILTIN_ROOT
    from persona_api.services.catalog_service import BUILTIN_ROOT as CATALOG_BUILTIN_ROOT
    from persona_api.services.runtime_factory import BUILTIN_ROOT as FACTORY_BUILTIN_ROOT

    # All three references point at the same on-disk Path.
    assert CORE_BUILTIN_ROOT == CATALOG_BUILTIN_ROOT == FACTORY_BUILTIN_ROOT
    # And critically, the same singleton instance (re-export, not a copy).
    assert CORE_BUILTIN_ROOT is CATALOG_BUILTIN_ROOT
    assert CORE_BUILTIN_ROOT is FACTORY_BUILTIN_ROOT


def test_deprecated_document_skills_resolve_via_alias_and_dedup() -> None:
    """Spec 16/17 packs were folded into ``document_generation`` (D-24-1).

    Coverage relocation: a persona declaring the deprecated names
    (``docx``/``pptx``/``xlsx``/``pdf_generation``) plus ``data_analysis``
    still resolves — the four format packs alias to the single
    ``document_generation`` (deduped), so chat-mode skill injection keeps
    working without persona-YAML changes.
    """
    scanner = SkillScanner(skill_paths=[BUILTIN_ROOT])
    declared = [
        "data_analysis",
        "docx_generation",
        "pptx_generation",
        "xlsx_generation",
        "pdf_generation",
    ]
    scanned = scanner.scan(declared_skills=declared)
    found_names = {s.name for s in scanned}
    # The four *_generation aliases collapse to one document_generation.
    assert found_names == {"data_analysis", "document_generation"}


def test_unified_skill_supports_the_relocated_formats() -> None:
    """The capability the four deleted packs provided survives at the new
    entry point: ``document_generation`` supports docx/pptx/xlsx/pdf (+ md/txt).
    """
    formats = set(supported_formats())
    assert {"docx", "pptx", "xlsx", "pdf"} <= formats
    assert {"md", "txt"} <= formats


@pytest.mark.asyncio
async def test_build_toolbox_advertises_use_skill_for_skilled_persona() -> None:
    """Runtime-factory wiring: a persona with scanned skills + an explicit
    ``tools`` allow-list (that does NOT name ``use_skill``) STILL advertises the
    ``use_skill`` tool the factory composes.

    Regression for the runtime bug where the toolbox allow-list filtered the
    composed ``use_skill`` meta-tool out — the model then never saw it and
    called the skill name directly (``document_generation``), hitting
    ``ToolNotAllowedError`` ("document_generation is not available"). The prior
    integration test masked this by cheating ``use_skill`` INTO the persona's
    ``tools`` list, which a real persona YAML never does.
    """
    from persona.schema.persona import Persona, PersonaIdentity
    from persona.skills import render_skill_index
    from persona_api.services.runtime_factory import RuntimeFactory

    persona = Persona(
        persona_id="p_skilled",
        identity=PersonaIdentity(
            name="Doc Bot",
            role="Writer",
            background="A persona that produces downloadable documents.",
        ),
        # A REAL persona's allow-list: capabilities only, never ``use_skill``.
        tools=["code_execution", "web_search", "web_fetch"],
        skills=["document_generation"],
    )
    # The factory never queries the engine in ``_build_toolbox``; a sentinel
    # engine is sufficient for this wiring assertion.
    factory = RuntimeFactory(
        rls_engine=object(),  # type: ignore[arg-type]
        embedder=None,  # type: ignore[arg-type]
        tier_registry=None,  # type: ignore[arg-type]
        turn_log_writer=None,  # type: ignore[arg-type]
        audit_root=BUILTIN_ROOT.parent,  # any extant dir
    )
    _scanner, scanned = factory._scan_skills(persona)  # noqa: SLF001
    assert "document_generation" in {s.name for s in scanned}

    toolbox = await factory._build_toolbox(persona, scanned)  # noqa: SLF001
    names = toolbox.names()  # type: ignore[attr-defined]
    assert "use_skill" in names, (
        "use_skill must be advertised for a skilled persona with an explicit "
        f"tools allow-list; got {names}"
    )
    # The skill index the agentic loop injects must list the enabled skill.
    index = render_skill_index(scanned)  # type: ignore[arg-type]
    assert "document_generation" in index

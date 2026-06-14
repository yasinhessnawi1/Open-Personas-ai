"""Spec 24 cross-spec integration — the full persona-declared-skills path.

End-to-end through the real bundled skills: a persona's ``skills: [...]`` list
mixing a collection ref, a deprecated alias, an explicit ``skill:`` ref, the new
``code_review`` builtin, and a bare name → the scanner expands collections
(D-24-6), resolves aliases (D-24-9), de-duplicates, and produces scanned specs
→ the index renders → the ``use_skill`` tool dispatches + validates parameters
(D-24-8) → composition discipline (D-24-4) holds. Proves the
persona-YAML → loader → runtime-callable path stays coherent across every
Spec 24 surface.
"""

from __future__ import annotations

import pytest
from persona.skills import (
    BUILTIN_ROOT,
    SkillInjector,
    SkillScanner,
    count_tokens,
    make_use_skill_tool,
    render_skill_index,
)
from persona.skills.composition import AdmissionResult, SkillCompositionState

pytestmark = pytest.mark.integration


def _scan(declared: list[str]):  # noqa: ANN202
    return SkillScanner([BUILTIN_ROOT]).scan(declared)


def test_mixed_declaration_resolves_to_expected_skill_set() -> None:
    # collection:research → web_research, data_analysis;
    # docx_generation → document_generation (alias);
    # skill:code_review → code_review; document_generation bare → dedup.
    specs = _scan(
        [
            "collection:research",
            "docx_generation",
            "skill:code_review",
            "document_generation",
        ]
    )
    names = [s.name for s in specs]
    assert names == ["web_research", "data_analysis", "document_generation", "code_review"]


def test_index_renders_every_resolved_skill() -> None:
    specs = _scan(["collection:document", "code_review"])
    index = render_skill_index(specs)
    assert "**document_generation**" in index
    assert "**code_review**" in index


@pytest.mark.asyncio
async def test_use_skill_validates_document_generation_parameters() -> None:
    specs = _scan(["collection:document"])
    tool = make_use_skill_tool(specs)
    ok = await tool.execute(skill_name="document_generation", parameters={"format": "pdf"})
    assert ok.is_error is False
    assert ok.data == {"skill_name": "document_generation", "parameters": {"format": "pdf"}}
    bad = await tool.execute(skill_name="document_generation", parameters={"format": "odt"})
    assert bad.is_error is True
    assert "Invalid parameters" in bad.content


@pytest.mark.asyncio
async def test_composition_chain_shares_budget_over_real_skills() -> None:
    # web_research (over budget) then document_generation: the injector budgets
    # the first; the shared accumulator carries into the second admission.
    [wr] = _scan(["web_research"])
    [doc] = _scan(["document_generation"])
    state = SkillCompositionState(budget=SkillInjector.TOKEN_BUDGET)
    injector = SkillInjector()

    first = state.admit(wr.name, content_tokens=wr.content_token_count)
    content = await injector.inject(wr)  # over budget → truncated to <= 2000
    state.record_injected(count_tokens(content))
    assert first is AdmissionResult.ADMITTED
    # document_generation (~1268 tokens) will not fit the budget already
    # consumed by the truncated web_research body → skipped whole, flag set.
    second = state.admit(doc.name, content_tokens=doc.content_token_count)
    assert second is AdmissionResult.SKIPPED_BUDGET
    assert state.budget_exceeded is True
    assert state.chain == ("web_research",)


def test_deprecated_aliases_keep_existing_personas_working() -> None:
    # The acceptance #2/#3 contract: a persona YAML written before Spec 24 with
    # only the old document_drafting name still loads to a usable skill.
    specs = _scan(["document_drafting"])
    assert [s.name for s in specs] == ["document_generation"]
    assert specs[0].tools_required == ["code_execution"]

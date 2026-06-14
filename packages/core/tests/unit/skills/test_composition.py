"""B3: skill-composition depth cap, cycle detection, shared budget (D-24-4)."""

from __future__ import annotations

import pytest
from persona.errors import SkillCompositionDepthError, SkillCycleError
from persona.skills.composition import (
    MAX_SKILL_COMPOSITION_DEPTH,
    AdmissionResult,
    SkillCompositionState,
)


def _state(budget: int = 2000) -> SkillCompositionState:
    return SkillCompositionState(budget=budget)


def test_first_skill_admitted_regardless_of_budget() -> None:
    s = _state(budget=10)
    assert s.admit("a", content_tokens=9999) is AdmissionResult.ADMITTED
    assert s.chain == ("a",)
    assert s.depth == 1


def test_chain_up_to_depth_three_admits() -> None:
    s = _state()
    for name in ("a", "b", "c"):
        assert s.admit(name, content_tokens=10) is AdmissionResult.ADMITTED
        s.record_injected(10)
    assert s.depth == MAX_SKILL_COMPOSITION_DEPTH
    assert s.chain == ("a", "b", "c")


def test_depth_four_raises_composition_depth_error() -> None:
    s = _state()
    for name in ("a", "b", "c"):
        s.admit(name, content_tokens=10)
        s.record_injected(10)
    with pytest.raises(SkillCompositionDepthError) as exc:
        s.admit("d", content_tokens=10)
    assert exc.value.context["requested"] == "d"
    assert exc.value.context["max_depth"] == "3"
    assert "a→b→c" in exc.value.context["chain"]


def test_cycle_raises_before_depth() -> None:
    s = _state()
    s.admit("a", content_tokens=10)
    s.record_injected(10)
    s.admit("b", content_tokens=10)
    s.record_injected(10)
    with pytest.raises(SkillCycleError) as exc:
        s.admit("a", content_tokens=10)
    assert exc.value.context["requested"] == "a"
    assert exc.value.context["chain"] == "a→b"


def test_cycle_checked_even_at_depth_cap() -> None:
    # A→B→C chain at the cap, re-requesting A → cycle, not depth (order matters).
    s = _state()
    for name in ("a", "b", "c"):
        s.admit(name, content_tokens=10)
        s.record_injected(10)
    with pytest.raises(SkillCycleError):
        s.admit("a", content_tokens=10)


def test_composed_skill_skipped_when_over_remaining_budget() -> None:
    s = _state(budget=100)
    s.admit("a", content_tokens=80)
    s.record_injected(80)  # remaining = 20
    result = s.admit("b", content_tokens=50)  # 50 > 20 → skip whole
    assert result is AdmissionResult.SKIPPED_BUDGET
    assert s.budget_exceeded is True
    assert s.chain == ("a",)  # b NOT added
    assert s.depth == 1


def test_composed_skill_admitted_when_fits_remaining() -> None:
    s = _state(budget=100)
    s.admit("a", content_tokens=60)
    s.record_injected(60)  # remaining = 40
    assert s.admit("b", content_tokens=40) is AdmissionResult.ADMITTED
    assert s.chain == ("a", "b")


def test_remaining_never_negative() -> None:
    s = _state(budget=50)
    s.admit("a", content_tokens=999)
    s.record_injected(999)
    assert s.remaining() == 0

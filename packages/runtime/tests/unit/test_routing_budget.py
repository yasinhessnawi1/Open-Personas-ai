"""Spec 23 T8 — budget evaluator (hard per-turn cap + soft session/day re-weight)."""

from __future__ import annotations

import pytest
from persona.backends.errors import BudgetExceededError
from persona_runtime.routing.model_scorer import ModelScore
from persona_runtime.routing.routing_budget import effective_weights, enforce_turn_cap
from persona_runtime.routing.scoring import ProfileWeights

_BASE = ProfileWeights(cost=0.40, quality=0.50, latency=0.10)


def _score(model_id: str, cost_cents: float) -> ModelScore:
    return ModelScore(model_id=model_id, total=0.5, cost_cents=cost_cents, axes={})


class TestTurnHardCap:
    def test_none_cap_is_noop(self) -> None:
        scored = [_score("a", 10.0), _score("b", 1.0)]
        assert enforce_turn_cap(scored, max_cents_per_turn=None, tier="frontier") == scored

    def test_filters_over_cap_candidates(self) -> None:
        scored = [_score("expensive", 10.0), _score("cheap", 1.0)]
        within = enforce_turn_cap(scored, max_cents_per_turn=5.0, tier="frontier")
        assert [s.model_id for s in within] == ["cheap"]

    def test_raises_when_none_fit(self) -> None:
        scored = [_score("a", 7.0), _score("b", 9.0)]
        with pytest.raises(BudgetExceededError) as exc:
            enforce_turn_cap(scored, max_cents_per_turn=5.0, tier="frontier")
        assert exc.value.context["scope"] == "per_turn"
        assert exc.value.context["tier"] == "frontier"
        assert exc.value.context["cap_cents"] == "5.0"
        assert exc.value.context["cheapest_candidate_cents"] == "7.0"


class TestSoftReweight:
    def test_below_threshold_returns_base_unchanged(self) -> None:
        # 50% of cap → no bias.
        w = effective_weights(_BASE, session_spent_cents=50.0, max_cents_per_session=100.0)
        assert w.cost == _BASE.cost
        assert w.quality == _BASE.quality

    def test_no_caps_returns_base(self) -> None:
        assert effective_weights(_BASE) is _BASE

    def test_approaching_session_cap_biases_toward_cost(self) -> None:
        # 90% of cap → halfway up the 0.8→1.0 ramp → cost up, quality down.
        w = effective_weights(_BASE, session_spent_cents=90.0, max_cents_per_session=100.0)
        assert w.cost > _BASE.cost
        assert w.quality < _BASE.quality

    def test_exceeded_cap_drives_full_cost_bias(self) -> None:
        # At/over the cap → fully cost-biased (cheapest capable).
        w = effective_weights(_BASE, session_spent_cents=100.0, max_cents_per_session=100.0)
        assert w.cost == 1.0
        assert w.quality == 0.0
        assert w.latency == 0.0

    def test_day_cap_cooldown_independent_of_session(self) -> None:
        w = effective_weights(_BASE, day_spent_cents=200.0, max_cents_per_day=200.0)
        assert w.cost == 1.0

    def test_max_of_session_and_day_pressure_wins(self) -> None:
        # Session at 50% (no bias), day at 100% (full bias) → full bias.
        w = effective_weights(
            _BASE,
            session_spent_cents=50.0,
            max_cents_per_session=100.0,
            day_spent_cents=200.0,
            max_cents_per_day=200.0,
        )
        assert w.cost == 1.0

    def test_deterministic(self) -> None:
        a = effective_weights(_BASE, session_spent_cents=90.0, max_cents_per_session=100.0)
        b = effective_weights(_BASE, session_spent_cents=90.0, max_cents_per_session=100.0)
        assert (a.cost, a.quality, a.latency) == (b.cost, b.quality, b.latency)

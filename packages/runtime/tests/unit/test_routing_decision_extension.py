"""Spec 23 T6 — RoutingDecision additive extension (D-23-X-routing-decision-extension)."""

from __future__ import annotations

import pytest
from persona_runtime.routing.types import RoutingDecision
from pydantic import ValidationError


class TestAdditiveBackwardCompat:
    def test_existing_minimal_construction_still_valid(self) -> None:
        # A Spec 05/18-style construction with NONE of the new fields must work
        # byte-identically and default the new fields to empties/False.
        d = RoutingDecision(
            tier="frontier",
            model="claude-sonnet-4-6",
            rationale="first_turn → frontier",
            candidates_considered=("frontier", "mid", "small"),
        )
        assert d.model_candidates == ()
        assert d.score_vector == {}
        assert d.weights_used == {}
        assert d.model_fallback_engaged is False
        assert d.model_fallback_reason is None
        # Spec 18 tier-level fallback fields are untouched + independent.
        assert d.fallback_triggered is False
        assert d.fallback_reason is None

    def test_still_frozen_and_extra_forbid(self) -> None:
        d = RoutingDecision(tier="mid", model="m", rationale="r", candidates_considered=("mid",))
        with pytest.raises(ValidationError):
            d.model_fallback_engaged = True  # type: ignore[misc]
        with pytest.raises(ValidationError):
            RoutingDecision(
                tier="mid",
                model="m",
                rationale="r",
                candidates_considered=("mid",),
                bogus=1,  # type: ignore[call-arg]
            )


class TestModelSelectionFields:
    def test_new_fields_populate(self) -> None:
        d = RoutingDecision(
            tier="frontier",
            model="anthropic/claude-3.5-sonnet",
            rationale="intelligent: best=anthropic/claude-3.5-sonnet score=0.91",
            candidates_considered=("frontier",),
            model_candidates=("anthropic/claude-3.5-sonnet", "deepseek/deepseek-chat"),
            score_vector={"cost": 0.5, "quality": 0.93, "latency": 0.7},
            weights_used={"cost": 0.4, "quality": 0.5, "latency": 0.1},
        )
        assert d.model == "anthropic/claude-3.5-sonnet"
        assert "deepseek/deepseek-chat" in d.model_candidates
        assert d.score_vector["quality"] == 0.93
        assert d.weights_used["cost"] == 0.4

    def test_model_fallback_distinct_from_tier_fallback(self) -> None:
        d = RoutingDecision(
            tier="mid",
            model="mid-primary",
            rationale="fallback: metadata miss → rule-based slot-0",
            candidates_considered=("mid",),
            model_fallback_engaged=True,
            model_fallback_reason="metadata_miss",
        )
        assert d.model_fallback_engaged is True
        assert d.model_fallback_reason == "metadata_miss"
        # Tier-level fallback stays False — the two layers are independent.
        assert d.fallback_triggered is False

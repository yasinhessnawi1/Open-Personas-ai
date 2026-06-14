"""Spec 23 T7 — model scorer (capability gate + weighted-sum + tie-break)."""

from __future__ import annotations

from persona.backends.model_metadata import ModelMetadata
from persona_runtime.routing.model_scorer import filter_capable, score_models
from persona_runtime.routing.scoring import ProfileWeights
from persona_runtime.routing.types import RoutingContext

_DEFAULT_WEIGHTS = ProfileWeights(cost=0.40, quality=0.50, latency=0.10)


def _ctx(**overrides: object) -> RoutingContext:
    defaults: dict[str, object] = {
        "requires_vision": False,
        "estimated_input_tokens": 1000,
        "requires_strong_tools": False,
        "is_first_turn": False,
        "is_identity_sensitive": False,
        "is_boilerplate": False,
        "conversation_phase": "middle",
        "profile": "text_default",
    }
    defaults.update(overrides)
    return RoutingContext(**defaults)  # type: ignore[arg-type]


def _md(
    *,
    cost: float = 0.10,
    quality: float = 0.80,
    latency: float = 300.0,
    tools: bool = True,
    vision: bool = True,
    ctx_len: int = 200_000,
) -> ModelMetadata:
    return ModelMetadata(
        cost_input_per_1k_tokens=cost,
        cost_output_per_1k_tokens=cost,
        latency_p50_ms=latency,
        quality_benchmark=quality,
        tools_supported=tools,
        vision_supported=vision,
        context_length=ctx_len,
    )


class TestCapabilityGate:
    def test_vision_turn_excludes_non_vision_models(self) -> None:
        candidates = [("a/vision", _md(vision=True)), ("a/text", _md(vision=False))]
        survivors = filter_capable(candidates, _ctx(requires_vision=True))
        assert [m for m, _ in survivors] == ["a/vision"]

    def test_strong_tools_turn_excludes_non_tool_models(self) -> None:
        candidates = [("a/tools", _md(tools=True)), ("a/notools", _md(tools=False))]
        survivors = filter_capable(candidates, _ctx(requires_strong_tools=True))
        assert [m for m, _ in survivors] == ["a/tools"]

    def test_context_length_gate(self) -> None:
        candidates = [("a/big", _md(ctx_len=200_000)), ("a/small", _md(ctx_len=4_000))]
        survivors = filter_capable(candidates, _ctx(estimated_input_tokens=8_000))
        assert [m for m, _ in survivors] == ["a/big"]

    def test_all_filtered_returns_empty(self) -> None:
        candidates = [("a/text", _md(vision=False))]
        assert score_models(candidates, _ctx(requires_vision=True), _DEFAULT_WEIGHTS) == []


class TestWeightedSum:
    def test_higher_quality_wins_with_default_weights(self) -> None:
        # Equal cost + latency → quality (0.50 weight) decides.
        candidates = [("a/hi", _md(quality=0.95)), ("a/lo", _md(quality=0.60))]
        ranked = score_models(candidates, _ctx(), _DEFAULT_WEIGHTS)
        assert ranked[0].model_id == "a/hi"

    def test_cost_weight_picks_cheaper(self) -> None:
        # Criterion 5: a cost-heavy weight vector clearly picks the cheaper model
        # even when it is lower quality.
        candidates = [
            ("a/expensive_good", _md(cost=2.00, quality=0.95)),
            ("a/cheap_ok", _md(cost=0.05, quality=0.70)),
        ]
        cost_heavy = ProfileWeights(cost=0.90, quality=0.05, latency=0.05)
        ranked = score_models(candidates, _ctx(), cost_heavy)
        assert ranked[0].model_id == "a/cheap_ok"

    def test_score_vector_axes_present(self) -> None:
        ranked = score_models([("a/m", _md())], _ctx(), _DEFAULT_WEIGHTS)
        assert set(ranked[0].axes) == {"cost", "quality", "latency"}

    def test_single_candidate_axes_are_neutral_one(self) -> None:
        # max==min on cost/latency → both normalise to 1.0 (no differentiation).
        ranked = score_models([("a/m", _md(quality=0.7))], _ctx(), _DEFAULT_WEIGHTS)
        assert ranked[0].axes["cost"] == 1.0
        assert ranked[0].axes["latency"] == 1.0
        assert ranked[0].axes["quality"] == 0.7


class TestLatencyOverride:
    def test_live_latency_override_beats_published(self) -> None:
        # Two models equal except published latency; an override makes the
        # nominally-slower model actually faster → it wins on a latency-heavy vec.
        candidates = [("a/x", _md(latency=200.0)), ("a/y", _md(latency=1000.0))]
        latency_heavy = ProfileWeights(cost=0.0, quality=0.0, latency=1.0)
        # Override: y is actually 50ms (warmed tracker), x has no samples.
        overrides = {"a/y": 50.0}
        ranked = score_models(candidates, _ctx(), latency_heavy, latency_override=overrides.get)
        assert ranked[0].model_id == "a/y"


class TestDeterminismAndTieBreak:
    def test_identical_inputs_identical_order(self) -> None:
        candidates = [("a/m1", _md(quality=0.8)), ("a/m2", _md(quality=0.8))]
        r1 = score_models(candidates, _ctx(), _DEFAULT_WEIGHTS)
        r2 = score_models(candidates, _ctx(), _DEFAULT_WEIGHTS)
        assert [s.model_id for s in r1] == [s.model_id for s in r2]

    def test_tie_breaks_by_cost_then_model_id(self) -> None:
        # Equal quality + latency; a/cheap has lower cost → wins the tie.
        candidates = [("a/zzz", _md(cost=0.50)), ("a/cheap", _md(cost=0.05))]
        ranked = score_models(candidates, _ctx(), _DEFAULT_WEIGHTS)
        assert ranked[0].model_id == "a/cheap"

    def test_full_tie_breaks_by_model_id(self) -> None:
        # Truly identical metadata → tie-break on model_id ascending.
        candidates = [("a/zzz", _md()), ("a/aaa", _md())]
        ranked = score_models(candidates, _ctx(), _DEFAULT_WEIGHTS)
        assert ranked[0].model_id == "a/aaa"

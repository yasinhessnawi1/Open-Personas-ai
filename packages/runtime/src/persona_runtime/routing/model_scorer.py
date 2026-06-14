"""Spec 23 model-within-tier scorer (T7; D-23-X-scoring-shape, D-23-1, D-23-4, D-23-6).

A deterministic scorer that ranks the candidate models in a tier's MODELS list
on cost / quality / latency, AFTER a hard capability gate. The model-layer
analogue of Spec 18's :func:`persona_runtime.routing.scoring.score_tier` — same
weighted-sum idiom one granularity down — so the codebase has one scoring shape,
not two. It reuses Spec 18's :class:`ProfileWeights` (D-23-1: defaults are the
``text_default`` profile, cost 0.40 / quality 0.50 / latency 0.10).

Pipeline (D-23-X-scoring-shape):

1. **Hard capability pre-gate** — vision / strong-tools / context-length, per
   model (finer than Spec 18 Layer 1's per-tier filter,
   D-23-X-capability-filter-layering). A model that fails any required capability
   is dropped, never down-weighted (R-23-1 anti-pattern: no soft-gating).
2. **Normalised weighted-sum** — ``quality_benchmark`` is already absolute
   ``[0,1]`` (D-23-4) and used directly; cost and latency have incommensurable
   raw units (cents, ms) so they are min-max normalised ACROSS the surviving
   candidate set (cheapest / fastest → 1.0). When an axis does not differentiate
   (max == min), every candidate scores 1.0 on it.
3. **Lexicographic tie-break** — equal totals break by cost ascending, then
   ``model_id`` ascending, so the choice is reproducible (criterion 4).

Determinism: the result is a pure function of the candidate list + metadata
snapshot + weights + the latency value resolved at call time (D-23-6 — the live
:class:`FirstTokenLatencyTracker` value enters via ``latency_override``; tests
freeze it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Callable

    from persona.backends.model_metadata import ModelMetadata

    from persona_runtime.routing.scoring import ProfileWeights
    from persona_runtime.routing.types import RoutingContext

__all__ = ["ModelScore", "filter_capable", "score_models"]

# Conservative output-token estimate for the per-turn cost calc — same value as
# Spec 18 D-18-5 (``scoring._ESTIMATED_OUTPUT_TOKENS_DEFAULT``) so model-layer and
# tier-layer cost estimates agree.
_ESTIMATED_OUTPUT_TOKENS: Final[int] = 500

Candidate = tuple[str, "ModelMetadata"]


@dataclass(frozen=True)
class ModelScore:
    """One candidate's score (T7).

    Attributes:
        model_id: The provider-prefixed model id.
        total: The weighted-sum total (higher = better for this turn).
        cost_cents: The estimated per-turn cost in cents (the lexicographic
            tie-break key and the budget evaluator's input, T8).
        axes: The normalised per-axis sub-scores
            (``{"cost", "quality", "latency"}``) carried onto
            :attr:`RoutingDecision.score_vector` for the audit trail (criterion 10).
    """

    model_id: str
    total: float
    cost_cents: float
    axes: dict[str, float] = field(default_factory=dict)


def _per_turn_cost_cents(md: ModelMetadata, estimated_input_tokens: int) -> float:
    """Estimated per-turn cost in cents (same formula as Spec 18 ``score_tier``)."""
    return (
        md.cost_input_per_1k_tokens * estimated_input_tokens / 1000.0
        + md.cost_output_per_1k_tokens * _ESTIMATED_OUTPUT_TOKENS / 1000.0
    )


def filter_capable(candidates: list[Candidate], context: RoutingContext) -> list[Candidate]:
    """Drop candidates that fail a required hard capability (D-23-X-capability-filter-layering).

    Vision-required turns keep only ``vision_supported`` models; strong-tool turns
    keep only ``tools_supported`` models; every candidate must have a
    ``context_length`` ≥ the turn's ``estimated_input_tokens``. Capabilities are a
    hard gate, never a weight — a high score must never select an incapable model.
    """
    survivors: list[Candidate] = []
    for model_id, md in candidates:
        if context.requires_vision and not md.vision_supported:
            continue
        if context.requires_strong_tools and not md.tools_supported:
            continue
        if md.context_length < context.estimated_input_tokens:
            continue
        survivors.append((model_id, md))
    return survivors


def _normalise_lower_is_better(values: dict[str, float]) -> dict[str, float]:
    """Min-max normalise so the LOWEST raw value scores 1.0 (cost / latency)."""
    if not values:
        return {}
    lo = min(values.values())
    hi = max(values.values())
    if hi == lo:
        return dict.fromkeys(values, 1.0)
    span = hi - lo
    return {k: (hi - v) / span for k, v in values.items()}


def score_models(
    candidates: list[Candidate],
    context: RoutingContext,
    weights: ProfileWeights,
    *,
    latency_override: Callable[[str], float | None] | None = None,
) -> list[ModelScore]:
    """Capability-gate, score, and rank ``candidates`` best-first (T7).

    Args:
        candidates: ``(model_id, ModelMetadata)`` pairs — the tier's MODELS list.
        context: The turn's routing context (capability requirements + tokens).
        weights: The cost / quality / latency weights (persona override or the
            D-23-1 ``text_default`` default).
        latency_override: Optional ``model_id → latency_ms | None`` callable
            supplying the live :class:`FirstTokenLatencyTracker` value when a
            model has ≥ N samples (D-23-6); ``None`` (or a ``None`` return) falls
            back to ``ModelMetadata.latency_p50_ms``.

    Returns:
        The capability-passing candidates as :class:`ModelScore`, sorted
        best-first (``total`` desc, then cost asc, then ``model_id`` asc). Empty
        when every candidate fails the capability gate.
    """
    survivors = filter_capable(candidates, context)
    if not survivors:
        return []

    costs = {mid: _per_turn_cost_cents(md, context.estimated_input_tokens) for mid, md in survivors}
    latencies: dict[str, float] = {}
    for mid, md in survivors:
        observed = latency_override(mid) if latency_override is not None else None
        latencies[mid] = observed if observed is not None else md.latency_p50_ms

    norm_cost = _normalise_lower_is_better(costs)
    norm_latency = _normalise_lower_is_better(latencies)

    scores: list[ModelScore] = []
    for mid, md in survivors:
        axes = {
            "cost": norm_cost[mid],
            "quality": md.quality_benchmark,  # already absolute [0,1] (D-23-4)
            "latency": norm_latency[mid],
        }
        total = (
            weights.cost * axes["cost"]
            + weights.quality * axes["quality"]
            + weights.latency * axes["latency"]
        )
        scores.append(ModelScore(model_id=mid, total=total, cost_cents=costs[mid], axes=axes))

    # Best-first: highest total; ties broken by cheapest, then model_id (D-23-X
    # determinism — no reliance on input/dict order).
    scores.sort(key=lambda s: (-s.total, s.cost_cents, s.model_id))
    return scores

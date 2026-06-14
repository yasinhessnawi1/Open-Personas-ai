"""Per-model routing metadata + resolver Protocol (Spec 23 T1).

Spec 18 added per-TIER :class:`~persona_runtime.tier.TierMetadata`; Spec 23 adds
the finer per-MODEL :class:`ModelMetadata` consumed by the model-within-tier
:class:`~persona_runtime.routing.intelligent_router.IntelligentRouter`. The unit
convention is identical to :class:`TierMetadata` (cents per 1k tokens,
milliseconds) so the model scorer reuses the Spec 18 ``score_tier`` arithmetic
one granularity down, and tier aggregates can derive from the model table
without a second hand-kept copy of any number
(D-23-X-metadata-placement: one authoritative numbers home in
``persona.backends.metadata``).

A :class:`ModelMetadataResolver` looks up metadata for a provider-prefixed model
id (``"anthropic/claude-3.5-sonnet"``). Resolvers chain OpenRouter → static →
miss (D-23-5); a miss (``None``) lets the IntelligentRouter degrade to
rule-based selection for that turn (criterion 9), never crashing.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["ModelMetadata", "ModelMetadataResolver"]


class ModelMetadata(BaseModel):
    """Per-model routing metadata for the Spec 23 model scorer (T1).

    Frozen Pydantic v2 + ``extra="forbid"``. The model-layer analogue of
    :class:`~persona_runtime.tier.TierMetadata`; the unit convention is
    identical (cents per 1k tokens, milliseconds) so the model scorer reuses
    the Spec 18 ``score_tier`` arithmetic one granularity down and tier
    aggregates can derive from this table (D-23-X-metadata-placement).

    ``quality_benchmark`` is normalised to ``[0.0, 1.0]`` at table-author time
    (D-23-4 — MMLU-Pro / GPQA-Diamond, NOT raw MMLU) so the scorer stays
    benchmark-agnostic. ``cost_verified_at_deploy`` mirrors
    :attr:`TierMetadata.cost_verified_at_deploy` (D-13-3 / D-20-1): ``False``
    flags best-estimate cost (e.g. NVIDIA — no public $/Mtok per R-23-2) and the
    scorer skips / down-weights the cost axis for that candidate.

    Attributes:
        cost_input_per_1k_tokens: Provider cost per 1k INPUT tokens (cents).
        cost_output_per_1k_tokens: Provider cost per 1k OUTPUT tokens (cents).
        latency_p50_ms: Published / best-estimate first-token p50 latency (ms).
            The live
            :class:`~persona_runtime.routing.latency.FirstTokenLatencyTracker`
            overrides this once a model has ≥ N samples (D-23-6).
        quality_benchmark: Normalised quality score in ``[0.0, 1.0]`` (D-23-4).
        tools_supported: Whether the model supports native tool calling — a
            model-level capability hard-gate (D-23-X-capability-filter-layering).
        vision_supported: Whether the model accepts image input — capability gate.
        context_length: Maximum context window (tokens) — capability gate.
        cost_verified_at_deploy: ``False`` → cost is best-estimate; the scorer
            skips / down-weights the cost axis (D-13-3 / D-20-1 precedent).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cost_input_per_1k_tokens: float = Field(ge=0.0)
    cost_output_per_1k_tokens: float = Field(ge=0.0)
    latency_p50_ms: float = Field(ge=0.0)
    quality_benchmark: float = Field(ge=0.0, le=1.0)
    tools_supported: bool
    vision_supported: bool
    context_length: int = Field(gt=0)
    cost_verified_at_deploy: bool = True


@runtime_checkable
class ModelMetadataResolver(Protocol):
    """Lookup interface: provider-prefixed model id → :class:`ModelMetadata` | None.

    Implementations chain (D-23-5): the OpenRouter catalog resolver (primary,
    broad coverage), the static per-provider tables (authoritative fallback),
    and the chained resolver that walks them. A ``None`` return is a metadata
    miss — the IntelligentRouter degrades to rule-based selection for that turn
    (criterion 9), never crashing.

    The ``model_id`` is the canonical provider-prefixed form
    (``"anthropic/claude-3.5-sonnet"``). Resolvers strip dynamic routing
    variants (``:nitro`` etc.) themselves where relevant (D-22-6).
    """

    def resolve(self, model_id: str) -> ModelMetadata | None:
        """Return metadata for ``model_id``, or ``None`` on a miss."""
        ...

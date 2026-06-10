"""Spec 20 T14 — NVIDIA launch-set TierMetadata registry (D-20-1; R-20-1, R-20-4, R-20-7).

Static lookup table mapping the D-20-1 launch NVIDIA model IDs to recommended
:class:`~persona_runtime.tier.TierMetadata` defaults. Used by operators (and
tests) as a starting point for per-tier metadata — the actual deployment can
still override every field via the ``PERSONA_<TIER>_*`` env-var schema read by
:func:`~persona_runtime.tier.tier_metadata_from_env`.

**verify-at-deploy convention** (D-13-3 precedent; R-20-4 finding): NVIDIA does
not publish authoritative ``$/Mtok`` on the hosted catalog — the free tier is
rate-limit gated and production deployments need AI Enterprise. The cost
fields here therefore carry **best-estimate mid-range values** and the entries
set :attr:`TierMetadata.cost_verified_at_deploy` to ``False`` to flag
operators they must measure-and-override before relying on Layer 2 cost
weighting.

**reasoning-capable flag** (D-18-5 quality-proxy boost; D-20-1): Nemotron-3
Super 120b (via ``enable_thinking``) and Nano-Omni 30b reasoning variant are
flagged ``reasoning_capable=True``; the chat-primary 49b-v1.5 stays ``False``.
The scorer (:func:`persona_runtime.routing.scoring.score_tier`) up-weights
``reasoning_capable=True`` tiers on hard turns (``quality_proxy >= 0.5``).

**Latency / throughput estimates** sourced from R-20-1 (model card audit) and
R-20-7 (image-gen profile measurements extrapolated for inference); ranges
chosen at midpoint of confidence band. Operators should re-measure against
their NIM deployment.
"""

from __future__ import annotations

from persona_runtime.tier import TierMetadata

__all__ = [
    "NVIDIA_LAUNCH_MODEL_METADATA",
    "nvidia_metadata_for_model",
]


# --- Launch set per D-20-1 ----------------------------------------------------
#
# Three chat / reasoning surfaces; the imagegen launch model (FLUX.2-klein-4b)
# lives outside the chat TierRegistry path and is handled by Spec 20 T16's
# MultiModelImageBackend.

NVIDIA_LAUNCH_MODEL_METADATA: dict[str, TierMetadata] = {
    # Chat primary — 128k confirmed context, native tool calling, NOT a
    # dedicated reasoning model (reasoning_capable=False).
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": TierMetadata(
        # R-20-4: NVIDIA does not publish $/Mtok; best-estimate 0.30 / 0.60
        # cents per 1k (mid-range vs llama-3.3 hosted pricing on other
        # providers). cost_verified_at_deploy=False signals operator override.
        cost_input_per_1k_tokens=0.30,
        cost_output_per_1k_tokens=0.60,
        # R-20-1: 200-400ms first-token estimate; midpoint 300ms.
        first_token_latency_ms=300.0,
        # R-20-1: 30-60 tps estimate; midpoint 45.
        throughput_tokens_per_sec=45.0,
        # Per model card — 128k = 131072 tokens.
        context_window=131072,
        tool_strength="strong",
        reasoning_capable=False,
        cost_verified_at_deploy=False,
    ),
    # Chat long-context + reasoning (via enable_thinking extra_body flag) —
    # 1M context, NVIDIA's flagship agentic-reasoning model.
    "nvidia/nemotron-3-super-120b-a12b": TierMetadata(
        cost_input_per_1k_tokens=1.50,
        cost_output_per_1k_tokens=7.50,
        # R-20-1: 400-800ms first-token estimate; midpoint 600ms.
        first_token_latency_ms=600.0,
        # R-20-1: 20-40 tps estimate; midpoint 30.
        throughput_tokens_per_sec=30.0,
        # Per model card — 1M context window (verify served context at deploy
        # since served context may differ from advertised).
        context_window=1_000_000,
        tool_strength="strong",
        reasoning_capable=True,
        cost_verified_at_deploy=False,
    ),
    # Reasoning + vision (omni-modal: image/video/speech/text). Cheaper
    # reasoning option than 120b-a12b. 30B total / 3B active MoE.
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": TierMetadata(
        cost_input_per_1k_tokens=0.15,
        cost_output_per_1k_tokens=0.30,
        # R-20-1: 200-400ms first-token estimate; midpoint 300ms.
        first_token_latency_ms=300.0,
        # R-20-1: 40-70 tps estimate; midpoint 55.
        throughput_tokens_per_sec=55.0,
        # R-20-1 modelcard fetch failed — conservative 32k default; operator
        # MUST re-measure against actual served context.
        context_window=32768,
        tool_strength="strong",
        reasoning_capable=True,
        cost_verified_at_deploy=False,
    ),
}


def nvidia_metadata_for_model(model_id: str) -> TierMetadata | None:
    """Return the recommended :class:`TierMetadata` for an NVIDIA launch model.

    Args:
        model_id: Provider-prefixed model ID, e.g.
            ``"nvidia/llama-3.3-nemotron-super-49b-v1.5"``.

    Returns:
        The launch-set :class:`TierMetadata` recommendation when ``model_id``
        is a D-20-1 launch entry; ``None`` for any other model (operators are
        expected to populate metadata via the
        :func:`~persona_runtime.tier.tier_metadata_from_env` env-var path
        for non-launch models).
    """
    return NVIDIA_LAUNCH_MODEL_METADATA.get(model_id)

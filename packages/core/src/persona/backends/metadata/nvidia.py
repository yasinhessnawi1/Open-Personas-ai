"""NVIDIA (Nemotron / NIM) static model metadata — the authoritative numbers home.

Spec 23 D-23-X-metadata-placement: these rows are the **single hand-kept copy**
of the NVIDIA launch-set per-model numbers. The Spec 20 tier table
(:data:`persona_runtime.routing.nvidia_models.NVIDIA_LAUNCH_MODEL_METADATA`)
DERIVES its :class:`TierMetadata` from these rows + tier-only fields
(throughput / tool_strength / reasoning_capable) — no second copy of cost,
latency, context, or the verify-at-deploy flag.

``cost_verified_at_deploy=False`` on every row: NVIDIA publishes no authoritative
``$/Mtok`` on the hosted catalog (R-20-4 / R-23-2 — free tier is rate-limit
gated, production is AI-Enterprise + own GPU). The cost fields are best-estimate
mid-range; the scorer skips / down-weights the cost axis for these candidates and
operators must measure-and-override at deploy. Quality is a normalised
best-estimate (Nemotron technical reports, R-23-2). Cost unit = cents per 1k
tokens.
"""

from __future__ import annotations

from persona.backends.model_metadata import ModelMetadata

__all__ = ["MODELS"]

MODELS: dict[str, ModelMetadata] = {
    # Chat primary — 128k context, native tools, NOT a dedicated reasoning model.
    "nvidia/llama-3.3-nemotron-super-49b-v1.5": ModelMetadata(
        cost_input_per_1k_tokens=0.30,
        cost_output_per_1k_tokens=0.60,
        latency_p50_ms=300.0,
        quality_benchmark=0.70,
        tools_supported=True,
        vision_supported=False,
        context_length=131_072,
        cost_verified_at_deploy=False,
    ),
    # Long-context + reasoning (enable_thinking) — 1M context, flagship.
    "nvidia/nemotron-3-super-120b-a12b": ModelMetadata(
        cost_input_per_1k_tokens=1.50,
        cost_output_per_1k_tokens=7.50,
        latency_p50_ms=600.0,
        quality_benchmark=0.82,
        tools_supported=True,
        vision_supported=False,
        context_length=1_000_000,
        cost_verified_at_deploy=False,
    ),
    # Reasoning + vision (omni-modal). Cheaper reasoning option; 30B/3B MoE.
    "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning": ModelMetadata(
        cost_input_per_1k_tokens=0.15,
        cost_output_per_1k_tokens=0.30,
        latency_p50_ms=300.0,
        quality_benchmark=0.66,
        tools_supported=True,
        vision_supported=True,
        context_length=32_768,
        cost_verified_at_deploy=False,
    ),
}

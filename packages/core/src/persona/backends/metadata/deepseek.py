"""DeepSeek static model metadata (Spec 23 T3; D-23-X-metadata-placement).

Pricing from api-docs.deepseek.com/quick_start/pricing (published,
``cost_verified_at_deploy=True``); cost unit = cents per 1k tokens =
``$/Mtok × 0.1``. Quality normalised to ``[0.0, 1.0]`` from the DeepSeek-V3
technical report (MMLU-Pro / GPQA, R-23-2). Starter set — operators extend per
MAINTENANCE.md (D-23-3).
"""

from __future__ import annotations

from persona.backends.model_metadata import ModelMetadata

__all__ = ["MODELS"]

MODELS: dict[str, ModelMetadata] = {
    # $0.27 / $1.10 per Mtok. No vision.
    "deepseek/deepseek-chat": ModelMetadata(
        cost_input_per_1k_tokens=0.027,
        cost_output_per_1k_tokens=0.11,
        latency_p50_ms=600.0,
        quality_benchmark=0.76,
        tools_supported=True,
        vision_supported=False,
        context_length=128_000,
    ),
    # $0.55 / $2.19 per Mtok. Reasoning model; no vision; slower first token.
    "deepseek/deepseek-reasoner": ModelMetadata(
        cost_input_per_1k_tokens=0.055,
        cost_output_per_1k_tokens=0.219,
        latency_p50_ms=900.0,
        quality_benchmark=0.81,
        tools_supported=True,
        vision_supported=False,
        context_length=128_000,
    ),
}

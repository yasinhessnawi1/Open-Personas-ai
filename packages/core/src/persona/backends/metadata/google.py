"""Google (Gemini) static model metadata (Spec 23 T3; D-23-X-metadata-placement).

Pricing from ai.google.dev/gemini-api/docs/pricing (published,
``cost_verified_at_deploy=True``); cost unit = cents per 1k tokens =
``$/Mtok × 0.1``. Quality normalised to ``[0.0, 1.0]`` from MMLU-Pro /
GPQA-Diamond (R-23-2). Starter set — operators extend per MAINTENANCE.md (D-23-3).
"""

from __future__ import annotations

from persona.backends.model_metadata import ModelMetadata

__all__ = ["MODELS"]

MODELS: dict[str, ModelMetadata] = {
    # $1.00 / $10 per Mtok.
    "google/gemini-2.5-pro": ModelMetadata(
        cost_input_per_1k_tokens=0.10,
        cost_output_per_1k_tokens=1.00,
        latency_p50_ms=500.0,
        quality_benchmark=0.89,
        tools_supported=True,
        vision_supported=True,
        context_length=1_000_000,
    ),
    # $0.30 / $2.50 per Mtok.
    "google/gemini-2.5-flash": ModelMetadata(
        cost_input_per_1k_tokens=0.03,
        cost_output_per_1k_tokens=0.25,
        latency_p50_ms=300.0,
        quality_benchmark=0.78,
        tools_supported=True,
        vision_supported=True,
        context_length=1_000_000,
    ),
}

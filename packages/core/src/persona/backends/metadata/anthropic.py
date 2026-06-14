"""Anthropic (Claude) static model metadata (Spec 23 T3; D-23-X-metadata-placement).

Pricing from anthropic.com/pricing (published, ``cost_verified_at_deploy=True``);
cost unit = cents per 1k tokens = ``$/Mtok × 0.1``. Quality normalised to
``[0.0, 1.0]`` from MMLU-Pro / GPQA-Diamond (R-23-2). Starter set — operators
extend per MAINTENANCE.md (D-23-3).
"""

from __future__ import annotations

from persona.backends.model_metadata import ModelMetadata

__all__ = ["MODELS"]

MODELS: dict[str, ModelMetadata] = {
    # $3 / $15 per Mtok.
    "anthropic/claude-3.5-sonnet": ModelMetadata(
        cost_input_per_1k_tokens=0.30,
        cost_output_per_1k_tokens=1.50,
        latency_p50_ms=400.0,
        quality_benchmark=0.88,
        tools_supported=True,
        vision_supported=True,
        context_length=200_000,
    ),
    # $0.80 / $4 per Mtok.
    "anthropic/claude-3.5-haiku": ModelMetadata(
        cost_input_per_1k_tokens=0.08,
        cost_output_per_1k_tokens=0.40,
        latency_p50_ms=250.0,
        quality_benchmark=0.72,
        tools_supported=True,
        vision_supported=True,
        context_length=200_000,
    ),
}

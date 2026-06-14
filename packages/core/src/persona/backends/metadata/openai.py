"""OpenAI (GPT) static model metadata (Spec 23 T3; D-23-X-metadata-placement).

Pricing from openai.com/api/pricing (published, ``cost_verified_at_deploy=True``);
cost unit = cents per 1k tokens = ``$/Mtok × 0.1``. Quality normalised to
``[0.0, 1.0]`` from MMLU-Pro / GPQA-Diamond (R-23-2). Starter set — operators
extend per MAINTENANCE.md (D-23-3).
"""

from __future__ import annotations

from persona.backends.model_metadata import ModelMetadata

__all__ = ["MODELS"]

MODELS: dict[str, ModelMetadata] = {
    # $2.50 / $10 per Mtok.
    "openai/gpt-4o": ModelMetadata(
        cost_input_per_1k_tokens=0.25,
        cost_output_per_1k_tokens=1.00,
        latency_p50_ms=450.0,
        quality_benchmark=0.86,
        tools_supported=True,
        vision_supported=True,
        context_length=128_000,
    ),
    # $0.15 / $0.60 per Mtok.
    "openai/gpt-4o-mini": ModelMetadata(
        cost_input_per_1k_tokens=0.015,
        cost_output_per_1k_tokens=0.06,
        latency_p50_ms=300.0,
        quality_benchmark=0.70,
        tools_supported=True,
        vision_supported=True,
        context_length=128_000,
    ),
}

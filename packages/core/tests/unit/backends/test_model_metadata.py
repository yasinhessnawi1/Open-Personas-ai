"""Unit tests for the Spec 23 :class:`ModelMetadata` + resolver Protocol (T1)."""

from __future__ import annotations

import pytest
from persona.backends.model_metadata import ModelMetadata, ModelMetadataResolver
from pydantic import ValidationError


def _valid_kwargs() -> dict[str, object]:
    return {
        "cost_input_per_1k_tokens": 0.30,
        "cost_output_per_1k_tokens": 1.50,
        "latency_p50_ms": 300.0,
        "quality_benchmark": 0.85,
        "tools_supported": True,
        "vision_supported": False,
        "context_length": 200_000,
    }


class TestModelMetadataConstruction:
    def test_constructs_with_valid_fields(self) -> None:
        md = ModelMetadata(**_valid_kwargs())
        assert md.cost_input_per_1k_tokens == 0.30
        assert md.quality_benchmark == 0.85
        assert md.context_length == 200_000

    def test_cost_verified_defaults_true(self) -> None:
        md = ModelMetadata(**_valid_kwargs())
        assert md.cost_verified_at_deploy is True

    def test_is_frozen(self) -> None:
        md = ModelMetadata(**_valid_kwargs())
        with pytest.raises(ValidationError):
            md.quality_benchmark = 0.1  # type: ignore[misc]

    def test_rejects_unknown_field(self) -> None:
        with pytest.raises(ValidationError):
            ModelMetadata(**_valid_kwargs(), surprise=1)  # type: ignore[arg-type]


class TestModelMetadataBounds:
    def test_quality_benchmark_must_be_normalised(self) -> None:
        for bad in (-0.1, 1.1):
            with pytest.raises(ValidationError):
                ModelMetadata(**{**_valid_kwargs(), "quality_benchmark": bad})

    def test_cost_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            ModelMetadata(**{**_valid_kwargs(), "cost_input_per_1k_tokens": -1.0})

    def test_latency_must_be_non_negative(self) -> None:
        with pytest.raises(ValidationError):
            ModelMetadata(**{**_valid_kwargs(), "latency_p50_ms": -1.0})

    def test_context_length_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            ModelMetadata(**{**_valid_kwargs(), "context_length": 0})


class TestModelMetadataResolverProtocol:
    def test_runtime_checkable_accepts_conforming_impl(self) -> None:
        class _Stub:
            def resolve(self, model_id: str) -> ModelMetadata | None:
                return ModelMetadata(**_valid_kwargs()) if model_id == "hit" else None

        stub = _Stub()
        assert isinstance(stub, ModelMetadataResolver)
        assert stub.resolve("hit") is not None
        assert stub.resolve("miss") is None

    def test_runtime_checkable_rejects_non_conforming(self) -> None:
        class _NotAResolver:
            pass

        assert not isinstance(_NotAResolver(), ModelMetadataResolver)

"""Unit tests for Spec 23 T5 ChainedModelMetadataResolver (D-23-X-resolver-precedence)."""

from __future__ import annotations

from persona.backends.metadata.chained_resolver import ChainedModelMetadataResolver
from persona.backends.model_metadata import ModelMetadata, ModelMetadataResolver


class _MapResolver:
    """Tiny in-memory resolver for composition tests."""

    def __init__(self, table: dict[str, ModelMetadata]) -> None:
        self._table = table

    def resolve(self, model_id: str) -> ModelMetadata | None:
        return self._table.get(model_id)


def _md(quality: float, *, cost: float = 0.1) -> ModelMetadata:
    return ModelMetadata(
        cost_input_per_1k_tokens=cost,
        cost_output_per_1k_tokens=cost,
        latency_p50_ms=200.0,
        quality_benchmark=quality,
        tools_supported=True,
        vision_supported=False,
        context_length=100_000,
    )


class TestChainedResolverPrecedence:
    def test_satisfies_protocol(self) -> None:
        resolver = ChainedModelMetadataResolver(static=_MapResolver({}), openrouter=None)
        assert isinstance(resolver, ModelMetadataResolver)

    def test_static_wins_when_present(self) -> None:
        # D-23-X-resolver-precedence: curated (static) record is authoritative,
        # even when the model is ALSO in OpenRouter.
        static = _MapResolver({"a/b": _md(0.9)})
        openrouter = _MapResolver({"a/b": _md(0.5)})  # neutral catalog quality
        resolver = ChainedModelMetadataResolver(static=static, openrouter=openrouter)
        hit = resolver.resolve("a/b")
        assert hit is not None
        assert hit.quality_benchmark == 0.9  # static authored quality, not 0.5

    def test_openrouter_serves_coverage_when_static_misses(self) -> None:
        static = _MapResolver({})
        openrouter = _MapResolver({"long/tail": _md(0.5)})
        resolver = ChainedModelMetadataResolver(static=static, openrouter=openrouter)
        hit = resolver.resolve("long/tail")
        assert hit is not None
        assert hit.quality_benchmark == 0.5

    def test_both_miss_returns_none(self) -> None:
        resolver = ChainedModelMetadataResolver(
            static=_MapResolver({}), openrouter=_MapResolver({})
        )
        assert resolver.resolve("nope/none") is None

    def test_static_only_chain(self) -> None:
        resolver = ChainedModelMetadataResolver(
            static=_MapResolver({"a/b": _md(0.8)}), openrouter=None
        )
        assert resolver.resolve("a/b") is not None
        assert resolver.resolve("x/y") is None

    def test_openrouter_only_chain(self) -> None:
        resolver = ChainedModelMetadataResolver(
            static=None, openrouter=_MapResolver({"a/b": _md(0.5)})
        )
        assert resolver.resolve("a/b") is not None
        assert resolver.resolve("x/y") is None

    def test_empty_chain_returns_none(self) -> None:
        assert ChainedModelMetadataResolver(static=None, openrouter=None).resolve("a/b") is None

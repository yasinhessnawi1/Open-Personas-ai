"""Unit tests for the Spec 18 TierRegistry metadata extension (T04).

Covers :class:`TierMetadata` boundary discipline (frozen, ``extra="forbid"``,
field validation), :class:`TierConfig` back-compat (the new ``metadata`` field
defaults to ``None``), :meth:`TierRegistry.metadata_for` (lookup + fallback
chain + raises when nothing resolves), and :func:`tier_metadata_from_env`
(env-driven population — all six vars required; partial / malformed →
``None``).
"""

from __future__ import annotations

import pytest
from persona.backends import BackendConfig
from persona_runtime.errors import TierNotConfiguredError
from persona_runtime.tier import (
    TierConfig,
    TierMetadata,
    TierRegistry,
    tier_metadata_from_env,
    tier_registry_from_env,
)
from pydantic import ValidationError


def _dummy_backend_config() -> BackendConfig:
    return BackendConfig(provider="anthropic", model="claude-sonnet-4-6", api_key="sk-test")


def _full_metadata(
    *,
    cost_in: float = 0.3,
    cost_out: float = 1.5,
    latency_ms: float = 800.0,
    throughput: float = 60.0,
    context: int = 200000,
    tool: str = "strong",
) -> TierMetadata:
    return TierMetadata(
        cost_input_per_1k_tokens=cost_in,
        cost_output_per_1k_tokens=cost_out,
        first_token_latency_ms=latency_ms,
        throughput_tokens_per_sec=throughput,
        context_window=context,
        tool_strength=tool,  # type: ignore[arg-type]
    )


# ----- TierMetadata boundary --------------------------------------------------


class TestTierMetadataConstruction:
    def test_construction_with_all_fields(self) -> None:
        md = _full_metadata()
        assert md.cost_input_per_1k_tokens == pytest.approx(0.3)
        assert md.tool_strength == "strong"


class TestTierMetadataFrozen:
    def test_attribute_assignment_raises(self) -> None:
        md = _full_metadata()
        with pytest.raises(ValidationError):
            md.cost_input_per_1k_tokens = 99.0  # type: ignore[misc]


class TestTierMetadataExtraForbid:
    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TierMetadata(
                cost_input_per_1k_tokens=0.3,
                cost_output_per_1k_tokens=1.5,
                first_token_latency_ms=800.0,
                throughput_tokens_per_sec=60.0,
                context_window=200000,
                tool_strength="strong",
                undeclared="rogue",  # type: ignore[call-arg]
            )


class TestTierMetadataValidation:
    def test_negative_cost_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _full_metadata(cost_in=-0.1)

    def test_negative_latency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _full_metadata(latency_ms=-1.0)

    def test_zero_context_window_rejected(self) -> None:
        # Field has gt=0; zero is invalid.
        with pytest.raises(ValidationError):
            _full_metadata(context=0)

    def test_invalid_tool_strength_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _full_metadata(tool="excellent")


# ----- TierConfig back-compat -------------------------------------------------


class TestTierConfigBackCompat:
    def test_construction_without_metadata_defaults_to_none(self) -> None:
        cfg = TierConfig(name="mid", backend_config=_dummy_backend_config())
        assert cfg.metadata is None

    def test_construction_with_metadata(self) -> None:
        md = _full_metadata()
        cfg = TierConfig(name="mid", backend_config=_dummy_backend_config(), metadata=md)
        assert cfg.metadata is md


# ----- TierRegistry.metadata_for ---------------------------------------------


class TestTierRegistryMetadataFor:
    def test_returns_metadata_when_populated(self) -> None:
        md = _full_metadata(latency_ms=600.0)
        registry = TierRegistry(
            {
                "frontier": TierConfig(
                    name="frontier",
                    backend_config=_dummy_backend_config(),
                    metadata=md,
                ),
            }
        )
        assert registry.metadata_for("frontier") is md
        assert registry.metadata_for("frontier").first_token_latency_ms == pytest.approx(600.0)

    def test_returns_none_when_metadata_unset(self) -> None:
        registry = TierRegistry(
            {
                "mid": TierConfig(name="mid", backend_config=_dummy_backend_config()),
            }
        )
        assert registry.metadata_for("mid") is None

    def test_walks_fallback_chain_for_unconfigured_tier(self) -> None:
        # Asking for "frontier" with only "mid" configured falls back to mid.
        md = _full_metadata()
        registry = TierRegistry(
            {
                "mid": TierConfig(
                    name="mid",
                    backend_config=_dummy_backend_config(),
                    metadata=md,
                ),
            }
        )
        # frontier resolves to mid via the fallback chain (small → mid → frontier
        # reversed for resolve); metadata follows.
        assert registry.metadata_for("frontier") is md

    def test_raises_when_no_tier_configured(self) -> None:
        registry = TierRegistry({})
        with pytest.raises(TierNotConfiguredError):
            registry.metadata_for("frontier")

    def test_does_not_instantiate_backend(self) -> None:
        # metadata_for is read-only — must NOT trigger load_backend.
        cfg = TierConfig(
            name="mid",
            backend_config=_dummy_backend_config(),
            metadata=_full_metadata(),
        )
        registry = TierRegistry({"mid": cfg})
        # Empty cache before the lookup; still empty after — proves no
        # backend was instantiated.
        assert registry._cache == {}  # noqa: SLF001 — verifying the no-side-effect contract
        registry.metadata_for("mid")
        assert registry._cache == {}  # noqa: SLF001


# ----- tier_metadata_from_env ------------------------------------------------


class TestTierMetadataFromEnv:
    def test_returns_metadata_when_all_six_vars_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PERSONA_FRONTIER_COST_INPUT_PER_1K", "0.3")
        monkeypatch.setenv("PERSONA_FRONTIER_COST_OUTPUT_PER_1K", "1.5")
        monkeypatch.setenv("PERSONA_FRONTIER_FIRST_TOKEN_LATENCY_MS", "800")
        monkeypatch.setenv("PERSONA_FRONTIER_THROUGHPUT_TOKENS_PER_SEC", "60")
        monkeypatch.setenv("PERSONA_FRONTIER_CONTEXT_WINDOW", "200000")
        monkeypatch.setenv("PERSONA_FRONTIER_TOOL_STRENGTH", "strong")
        md = tier_metadata_from_env(prefix="PERSONA_FRONTIER_")
        assert md is not None
        assert md.cost_input_per_1k_tokens == pytest.approx(0.3)
        assert md.context_window == 200000
        assert md.tool_strength == "strong"

    def test_returns_none_when_no_vars_present(self) -> None:
        # No monkeypatch — relying on no PERSONA_NEWTIER_* env vars existing.
        assert tier_metadata_from_env(prefix="PERSONA_NEWTIER_NONEXISTENT_") is None

    def test_returns_none_when_partial_vars_present(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # 5/6 vars present — missing CONTEXT_WINDOW.
        monkeypatch.setenv("PERSONA_FRONTIER_COST_INPUT_PER_1K", "0.3")
        monkeypatch.setenv("PERSONA_FRONTIER_COST_OUTPUT_PER_1K", "1.5")
        monkeypatch.setenv("PERSONA_FRONTIER_FIRST_TOKEN_LATENCY_MS", "800")
        monkeypatch.setenv("PERSONA_FRONTIER_THROUGHPUT_TOKENS_PER_SEC", "60")
        monkeypatch.setenv("PERSONA_FRONTIER_TOOL_STRENGTH", "strong")
        assert tier_metadata_from_env(prefix="PERSONA_FRONTIER_") is None

    def test_returns_none_when_malformed_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PERSONA_FRONTIER_COST_INPUT_PER_1K", "not-a-float")
        monkeypatch.setenv("PERSONA_FRONTIER_COST_OUTPUT_PER_1K", "1.5")
        monkeypatch.setenv("PERSONA_FRONTIER_FIRST_TOKEN_LATENCY_MS", "800")
        monkeypatch.setenv("PERSONA_FRONTIER_THROUGHPUT_TOKENS_PER_SEC", "60")
        monkeypatch.setenv("PERSONA_FRONTIER_CONTEXT_WINDOW", "200000")
        monkeypatch.setenv("PERSONA_FRONTIER_TOOL_STRENGTH", "strong")
        assert tier_metadata_from_env(prefix="PERSONA_FRONTIER_") is None


# ----- tier_registry_from_env extends to metadata ----------------------------


class TestTierRegistryFromEnvWithMetadata:
    def test_per_tier_metadata_populated_when_env_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PERSONA_FRONTIER_PROVIDER", "anthropic")
        monkeypatch.setenv("PERSONA_FRONTIER_MODEL", "claude-opus-4-7")
        monkeypatch.setenv("PERSONA_FRONTIER_API_KEY", "sk-test")
        monkeypatch.setenv("PERSONA_FRONTIER_COST_INPUT_PER_1K", "1.5")
        monkeypatch.setenv("PERSONA_FRONTIER_COST_OUTPUT_PER_1K", "7.5")
        monkeypatch.setenv("PERSONA_FRONTIER_FIRST_TOKEN_LATENCY_MS", "1200")
        monkeypatch.setenv("PERSONA_FRONTIER_THROUGHPUT_TOKENS_PER_SEC", "40")
        monkeypatch.setenv("PERSONA_FRONTIER_CONTEXT_WINDOW", "200000")
        monkeypatch.setenv("PERSONA_FRONTIER_TOOL_STRENGTH", "strong")
        registry = tier_registry_from_env()
        md = registry.metadata_for("frontier")
        assert md is not None
        assert md.cost_input_per_1k_tokens == pytest.approx(1.5)
        assert md.context_window == 200000

    def test_metadata_none_when_env_partial(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("PERSONA_MID_PROVIDER", "anthropic")
        monkeypatch.setenv("PERSONA_MID_MODEL", "claude-haiku-4-5")
        monkeypatch.setenv("PERSONA_MID_API_KEY", "sk-test")
        # No metadata env vars — tier still configured, metadata is None.
        registry = tier_registry_from_env()
        assert registry.metadata_for("mid") is None


# ----- Spec 20 T14 — reasoning_capable + cost_verified_at_deploy -------------


class TestTierMetadataReasoningCapable:
    """Spec 20 T14 — additive ``reasoning_capable`` field (D-18-5 boost)."""

    def test_defaults_to_false(self) -> None:
        # Back-compat: existing constructions stay valid; flag defaults False.
        md = _full_metadata()
        assert md.reasoning_capable is False

    def test_constructs_with_true(self) -> None:
        md = TierMetadata(
            cost_input_per_1k_tokens=1.5,
            cost_output_per_1k_tokens=7.5,
            first_token_latency_ms=600.0,
            throughput_tokens_per_sec=30.0,
            context_window=1_000_000,
            tool_strength="strong",
            reasoning_capable=True,
        )
        assert md.reasoning_capable is True

    def test_frozen_after_construction(self) -> None:
        md = TierMetadata(
            cost_input_per_1k_tokens=1.5,
            cost_output_per_1k_tokens=7.5,
            first_token_latency_ms=600.0,
            throughput_tokens_per_sec=30.0,
            context_window=1_000_000,
            tool_strength="strong",
            reasoning_capable=True,
        )
        with pytest.raises(ValidationError):
            md.reasoning_capable = False  # type: ignore[misc]


class TestTierMetadataCostVerifiedAtDeploy:
    """Spec 20 T14 — D-13-3 verify-at-deploy convention surface."""

    def test_defaults_to_true(self) -> None:
        md = _full_metadata()
        assert md.cost_verified_at_deploy is True

    def test_constructs_with_false(self) -> None:
        # NVIDIA launch-set entries set this to False to flag best-estimate
        # cost values to operators (R-20-4 — NVIDIA doesn't publish $/Mtok).
        md = TierMetadata(
            cost_input_per_1k_tokens=0.30,
            cost_output_per_1k_tokens=0.60,
            first_token_latency_ms=300.0,
            throughput_tokens_per_sec=45.0,
            context_window=131072,
            tool_strength="strong",
            reasoning_capable=False,
            cost_verified_at_deploy=False,
        )
        assert md.cost_verified_at_deploy is False


# ----- Spec 20 T14 — env-var reading for new optional fields -----------------


class TestTierMetadataFromEnvReasoningCapable:
    """Spec 20 T14 — ``<PREFIX>REASONING_CAPABLE`` env-var support."""

    def _set_required_env(self, monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
        monkeypatch.setenv(f"{prefix}COST_INPUT_PER_1K", "0.3")
        monkeypatch.setenv(f"{prefix}COST_OUTPUT_PER_1K", "1.5")
        monkeypatch.setenv(f"{prefix}FIRST_TOKEN_LATENCY_MS", "800")
        monkeypatch.setenv(f"{prefix}THROUGHPUT_TOKENS_PER_SEC", "60")
        monkeypatch.setenv(f"{prefix}CONTEXT_WINDOW", "200000")
        monkeypatch.setenv(f"{prefix}TOOL_STRENGTH", "strong")

    def test_reasoning_capable_defaults_false_when_var_absent(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        self._set_required_env(monkeypatch, "PERSONA_FRONTIER_")
        md = tier_metadata_from_env(prefix="PERSONA_FRONTIER_")
        assert md is not None
        assert md.reasoning_capable is False

    @pytest.mark.parametrize("truthy", ["1", "true", "True", "TRUE", "yes", "on"])
    def test_reasoning_capable_reads_truthy_values(
        self, monkeypatch: pytest.MonkeyPatch, truthy: str
    ) -> None:
        self._set_required_env(monkeypatch, "PERSONA_FRONTIER_")
        monkeypatch.setenv("PERSONA_FRONTIER_REASONING_CAPABLE", truthy)
        md = tier_metadata_from_env(prefix="PERSONA_FRONTIER_")
        assert md is not None
        assert md.reasoning_capable is True

    @pytest.mark.parametrize("falsy", ["0", "false", "no", "off"])
    def test_reasoning_capable_reads_falsy_values(
        self, monkeypatch: pytest.MonkeyPatch, falsy: str
    ) -> None:
        self._set_required_env(monkeypatch, "PERSONA_FRONTIER_")
        monkeypatch.setenv("PERSONA_FRONTIER_REASONING_CAPABLE", falsy)
        md = tier_metadata_from_env(prefix="PERSONA_FRONTIER_")
        assert md is not None
        assert md.reasoning_capable is False

    def test_unknown_value_falls_back_to_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_required_env(monkeypatch, "PERSONA_FRONTIER_")
        monkeypatch.setenv("PERSONA_FRONTIER_REASONING_CAPABLE", "garbage")
        md = tier_metadata_from_env(prefix="PERSONA_FRONTIER_")
        assert md is not None
        assert md.reasoning_capable is False

    def test_optional_flag_does_not_gate_metadata_return(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The new optional flags must NOT cause partial-env behaviour — six
        # required vars present + no optional flag should still return metadata.
        self._set_required_env(monkeypatch, "PERSONA_MID_")
        md = tier_metadata_from_env(prefix="PERSONA_MID_")
        assert md is not None


class TestTierMetadataFromEnvCostVerifiedAtDeploy:
    """Spec 20 T14 — ``<PREFIX>COST_VERIFIED_AT_DEPLOY`` env-var support."""

    def _set_required_env(self, monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
        monkeypatch.setenv(f"{prefix}COST_INPUT_PER_1K", "0.3")
        monkeypatch.setenv(f"{prefix}COST_OUTPUT_PER_1K", "1.5")
        monkeypatch.setenv(f"{prefix}FIRST_TOKEN_LATENCY_MS", "800")
        monkeypatch.setenv(f"{prefix}THROUGHPUT_TOKENS_PER_SEC", "60")
        monkeypatch.setenv(f"{prefix}CONTEXT_WINDOW", "200000")
        monkeypatch.setenv(f"{prefix}TOOL_STRENGTH", "strong")

    def test_defaults_true_when_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_required_env(monkeypatch, "PERSONA_FRONTIER_")
        md = tier_metadata_from_env(prefix="PERSONA_FRONTIER_")
        assert md is not None
        assert md.cost_verified_at_deploy is True

    def test_reads_false_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._set_required_env(monkeypatch, "PERSONA_FRONTIER_")
        monkeypatch.setenv("PERSONA_FRONTIER_COST_VERIFIED_AT_DEPLOY", "false")
        md = tier_metadata_from_env(prefix="PERSONA_FRONTIER_")
        assert md is not None
        assert md.cost_verified_at_deploy is False


class TestTierMetadataFromEnvAllTiers:
    """T14 — parametrised verification that env-reader works for every tier prefix."""

    @pytest.mark.parametrize("prefix", ["PERSONA_FRONTIER_", "PERSONA_MID_", "PERSONA_SMALL_"])
    def test_reads_per_tier_prefix(self, monkeypatch: pytest.MonkeyPatch, prefix: str) -> None:
        monkeypatch.setenv(f"{prefix}COST_INPUT_PER_1K", "0.3")
        monkeypatch.setenv(f"{prefix}COST_OUTPUT_PER_1K", "1.5")
        monkeypatch.setenv(f"{prefix}FIRST_TOKEN_LATENCY_MS", "800")
        monkeypatch.setenv(f"{prefix}THROUGHPUT_TOKENS_PER_SEC", "60")
        monkeypatch.setenv(f"{prefix}CONTEXT_WINDOW", "200000")
        monkeypatch.setenv(f"{prefix}TOOL_STRENGTH", "strong")
        monkeypatch.setenv(f"{prefix}REASONING_CAPABLE", "true")
        md = tier_metadata_from_env(prefix=prefix)
        assert md is not None
        assert md.reasoning_capable is True

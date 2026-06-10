"""Unit tests for persona_runtime.tier (T03; D-05-3, D-05-4)."""

# ruff: noqa: SLF001, ARG001, ARG002 — tests reach into _resolve and use mock fixtures
#   with unused args; matches the spec-02/03/04 test-file convention.

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from persona.backends import BackendConfig
from persona_runtime.errors import TierNotConfiguredError
from persona_runtime.tier import (
    TierConfig,
    TierRegistry,
    tier_registry_from_env,
)

if TYPE_CHECKING:
    from collections.abc import Iterator


class _FakeBackend:
    """Stands in for a ChatBackend; records whether it was closed."""

    def __init__(self, marker: str, *, closer: str | None = "aclose") -> None:
        self.marker = marker
        self.closed = 0
        self._closer = closer
        if closer == "aclose":
            self.aclose = self._close  # type: ignore[method-assign]
        elif closer == "disconnect":
            self.disconnect = self._close  # type: ignore[attr-defined]

    async def _close(self) -> None:
        self.closed += 1


def _cfg(provider: str = "anthropic") -> BackendConfig:
    return BackendConfig(provider=provider, model="m", api_key=None)  # type: ignore[arg-type]


def _tier(name: str) -> TierConfig:
    return TierConfig(name=name, backend_config=_cfg())


@pytest.fixture
def patched_load(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, int]]:
    """Patch tier.load_backend to return a fresh _FakeBackend, counting calls per config id."""
    calls: dict[str, int] = {"count": 0}

    def fake_load(config: BackendConfig) -> _FakeBackend:
        calls["count"] += 1
        return _FakeBackend(marker=f"backend-{calls['count']}")

    monkeypatch.setattr("persona_runtime.tier.load_backend", fake_load)
    return calls


class TestLazyInstantiationAndCache:
    def test_get_instantiates_once_and_caches(self, patched_load: dict[str, int]) -> None:
        reg = TierRegistry({"frontier": _tier("frontier")})
        b1 = reg.get("frontier")
        b2 = reg.get("frontier")
        assert b1 is b2  # cached: same instance
        assert patched_load["count"] == 1  # load_backend called exactly once

    def test_unused_tier_is_not_instantiated(self, patched_load: dict[str, int]) -> None:
        reg = TierRegistry(
            {"frontier": _tier("frontier"), "mid": _tier("mid"), "small": _tier("small")}
        )
        reg.get("mid")
        assert patched_load["count"] == 1  # only mid was built; frontier/small untouched


class TestFallback:
    def test_unconfigured_tier_falls_back_small_to_mid_to_frontier(
        self, patched_load: dict[str, int]
    ) -> None:
        # Only frontier configured; asking for "mid" falls back to frontier.
        reg = TierRegistry({"frontier": _tier("frontier")})
        backend = reg.get("mid")
        assert backend is reg.get("frontier")  # same effective tier, same instance

    def test_fallback_prefers_small_then_mid_then_frontier(
        self, patched_load: dict[str, int]
    ) -> None:
        # mid + frontier configured, small missing; asking "small" -> mid (first in order).
        reg = TierRegistry({"mid": _tier("mid"), "frontier": _tier("frontier")})
        backend = reg.get("small")
        assert backend is reg.get("mid")

    def test_no_tiers_raises_tier_not_configured(self, patched_load: dict[str, int]) -> None:
        reg = TierRegistry({})
        with pytest.raises(TierNotConfiguredError) as exc_info:
            reg.get("frontier")
        assert exc_info.value.context["requested"] == "frontier"
        assert exc_info.value.context["configured"] == "(none)"


class TestAclose:
    @pytest.mark.asyncio
    async def test_aclose_disconnects_cached_backends_once(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        made: list[_FakeBackend] = []

        def fake_load(config: BackendConfig) -> _FakeBackend:
            b = _FakeBackend(marker=f"b{len(made)}")
            made.append(b)
            return b

        monkeypatch.setattr("persona_runtime.tier.load_backend", fake_load)
        reg = TierRegistry({"frontier": _tier("frontier"), "mid": _tier("mid")})
        reg.get("frontier")
        reg.get("mid")
        assert len(made) == 2

        await reg.aclose()
        assert all(b.closed == 1 for b in made)

    @pytest.mark.asyncio
    async def test_aclose_skips_uncached_tiers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        made: list[_FakeBackend] = []

        def fake_load(config: BackendConfig) -> _FakeBackend:
            b = _FakeBackend(marker="x")
            made.append(b)
            return b

        monkeypatch.setattr("persona_runtime.tier.load_backend", fake_load)
        reg = TierRegistry({"frontier": _tier("frontier"), "mid": _tier("mid")})
        reg.get("frontier")  # only frontier cached
        await reg.aclose()
        assert len(made) == 1  # mid was never instantiated

    @pytest.mark.asyncio
    async def test_aclose_is_idempotent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        b = _FakeBackend(marker="b")
        monkeypatch.setattr("persona_runtime.tier.load_backend", lambda _c: b)
        reg = TierRegistry({"frontier": _tier("frontier")})
        reg.get("frontier")
        await reg.aclose()
        await reg.aclose()  # second call: cache cleared, no error, no double-close
        assert b.closed == 1

    @pytest.mark.asyncio
    async def test_aclose_skips_backend_without_closer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        b = _FakeBackend(marker="b", closer=None)  # no aclose/disconnect
        monkeypatch.setattr("persona_runtime.tier.load_backend", lambda _c: b)
        reg = TierRegistry({"frontier": _tier("frontier")})
        reg.get("frontier")
        await reg.aclose()  # should not raise
        assert b.closed == 0

    @pytest.mark.asyncio
    async def test_aclose_honours_disconnect_method(self, monkeypatch: pytest.MonkeyPatch) -> None:
        b = _FakeBackend(marker="b", closer="disconnect")
        monkeypatch.setattr("persona_runtime.tier.load_backend", lambda _c: b)
        reg = TierRegistry({"frontier": _tier("frontier")})
        reg.get("frontier")
        await reg.aclose()
        assert b.closed == 1


class TestFromEnv:
    def test_builds_per_tier_when_provider_env_present(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Spec 20 D-20-17 case (b) — all three triplet vars REQUIRED for the
        # backward-compat per-tier path. Partial-triplet (1-2 of 3) now raises
        # ``IncompleteTierConfigError``; covered in
        # ``test_tier_registry_multimodel.py::TestPartialTriplet``.
        monkeypatch.setenv("PERSONA_FRONTIER_PROVIDER", "anthropic")
        monkeypatch.setenv("PERSONA_FRONTIER_MODEL", "claude-sonnet-4-6")
        monkeypatch.setenv("PERSONA_FRONTIER_API_KEY", "sk-ant-test")
        monkeypatch.setenv("PERSONA_MID_PROVIDER", "deepseek")
        monkeypatch.setenv("PERSONA_MID_MODEL", "deepseek-chat")
        monkeypatch.setenv("PERSONA_MID_API_KEY", "sk-deepseek-test")
        # small intentionally absent
        monkeypatch.delenv("PERSONA_SMALL_PROVIDER", raising=False)
        monkeypatch.delenv("PERSONA_SMALL_MODEL", raising=False)
        monkeypatch.delenv("PERSONA_SMALL_API_KEY", raising=False)
        monkeypatch.delenv("PERSONA_SMALL_MODELS", raising=False)

        reg = tier_registry_from_env()
        # frontier + mid configured; small unconfigured -> falls back (mid).
        assert reg._resolve("frontier") == "frontier"
        assert reg._resolve("mid") == "mid"
        assert reg._resolve("small") == "mid"  # fallback order: small->mid

    def test_single_backend_fallback_when_no_tiers(self, monkeypatch: pytest.MonkeyPatch) -> None:
        for prefix in ("FRONTIER", "MID", "SMALL"):
            for suffix in ("PROVIDER", "MODEL", "API_KEY", "MODELS"):
                monkeypatch.delenv(f"PERSONA_{prefix}_{suffix}", raising=False)
        monkeypatch.setenv("PERSONA_PROVIDER", "groq")
        monkeypatch.setenv("PERSONA_MODEL", "llama-3.1-8b-instant")

        reg = tier_registry_from_env()
        # All three tier names resolve (single backend served for each).
        assert reg._resolve("frontier") == "frontier"
        assert reg._resolve("mid") == "mid"
        assert reg._resolve("small") == "small"

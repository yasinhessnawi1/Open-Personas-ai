"""Unit tests for the open-core edition seams (Spec 33, Cluster A).

No DB, no network. Covers edition selection, the OwnerResolver / CreditsPolicy
impls, and the public-no-auth safety guard.
"""

from __future__ import annotations

import pytest
from persona_api.config import APIConfig, Edition
from persona_api.editions import (
    CloudOwnerResolver,
    CommunityOwnerResolver,
    MeteredCreditsPolicy,
    UnlimitedCreditsPolicy,
    build_credits_policy,
    build_owner_resolver,
    check_public_noauth_guard,
)
from persona_api.editions.guard import _is_loopback
from persona_api.errors import PublicNoAuthRefusedError


def test_edition_defaults_to_community(monkeypatch: pytest.MonkeyPatch) -> None:
    # The session autouse fixture sets PERSONA_EDITION=cloud; clear it to see the
    # product default.
    monkeypatch.delenv("PERSONA_EDITION", raising=False)
    assert APIConfig().edition is Edition.community


def test_edition_env_override_selects_cloud(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONA_EDITION", "cloud")
    assert APIConfig().edition is Edition.cloud


def test_explicit_kwarg_overrides_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PERSONA_EDITION", "cloud")
    assert APIConfig(edition=Edition.community).edition is Edition.community


def test_build_owner_resolver_selects_by_edition() -> None:
    cloud = build_owner_resolver(APIConfig(edition=Edition.cloud))
    community = build_owner_resolver(APIConfig(edition=Edition.community))
    assert isinstance(cloud, CloudOwnerResolver)
    assert isinstance(community, CommunityOwnerResolver)


def test_build_credits_policy_selects_by_edition() -> None:
    cloud = build_credits_policy(APIConfig(edition=Edition.cloud))
    community = build_credits_policy(APIConfig(edition=Edition.community))
    assert isinstance(cloud, MeteredCreditsPolicy)
    assert isinstance(community, UnlimitedCreditsPolicy)


@pytest.mark.asyncio
async def test_community_owner_resolver_returns_fixed_owner() -> None:
    resolver = CommunityOwnerResolver(owner_id="local-owner", email="local@localhost")

    async def _never(_token: str) -> object:  # pragma: no cover - must not be called
        raise AssertionError("community resolver must not verify a token")

    user = await resolver.resolve(object(), _never)  # type: ignore[arg-type]
    assert user.id == "local-owner"
    assert user.email == "local@localhost"


def test_unlimited_credits_policy_is_a_noop() -> None:
    policy = UnlimitedCreditsPolicy()
    eng = object()  # never touched — the policy ignores the engine
    assert policy.require_credits(rls_engine=eng, user_id="x") > 0  # type: ignore[arg-type]
    assert policy.get_balance(rls_engine=eng, user_id="x") > 0  # type: ignore[arg-type]
    # deduct/refund never raise and never touch the DB
    assert policy.deduct(rls_engine=eng, user_id="x", amount=1000, reason="t") > 0  # type: ignore[arg-type]
    assert policy.refund(rls_engine=eng, user_id="x", amount=1000, reason="t") > 0  # type: ignore[arg-type]
    assert policy.list_usage(rls_engine=eng, user_id="x", limit=10, offset=0) == []  # type: ignore[arg-type]
    assert policy.list_turn_usage(rls_engine=eng, limit=10, offset=0) == []  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("localhost", True),
        ("", True),
        ("127.0.0.5", True),
        ("0.0.0.0", False),
        ("::", False),
        ("192.168.1.10", False),
        ("api.example.com", False),
    ],
)
def test_is_loopback(host: str, loopback: bool) -> None:
    assert _is_loopback(host) is loopback


def test_guard_refuses_community_noauth_on_public_bind() -> None:
    config = APIConfig(edition=Edition.community, host="0.0.0.0", allow_public_noauth=False)
    with pytest.raises(PublicNoAuthRefusedError):
        check_public_noauth_guard(config)


def test_guard_allows_community_on_loopback() -> None:
    check_public_noauth_guard(
        APIConfig(edition=Edition.community, host="127.0.0.1", allow_public_noauth=False)
    )


def test_guard_allows_public_bind_with_explicit_optin() -> None:
    check_public_noauth_guard(
        APIConfig(edition=Edition.community, host="0.0.0.0", allow_public_noauth=True)
    )


def test_guard_never_gates_cloud() -> None:
    # cloud has an auth wall; a public bind is expected and allowed.
    check_public_noauth_guard(
        APIConfig(edition=Edition.cloud, host="0.0.0.0", allow_public_noauth=False)
    )

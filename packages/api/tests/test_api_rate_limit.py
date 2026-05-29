"""Rate limiter unit tests (spec 08, T09, §6).

No DB: the InMemory store + the RateLimiter window/limit logic. The Postgres
store contract is exercised in the integration suite (it needs a real DB).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from persona_api.errors import RateLimitExceededError
from persona_api.middleware.rate_limit import (
    InMemoryRateLimitStore,
    RateLimiter,
    RateLimitStore,
)

_T0 = datetime(2026, 5, 28, 12, 0, 30, tzinfo=UTC)  # mid-minute


def test_inmemory_store_satisfies_protocol() -> None:
    assert isinstance(InMemoryRateLimitStore(), RateLimitStore)


def test_under_limit_allows_and_decrements_remaining() -> None:
    limiter = RateLimiter(InMemoryRateLimitStore(), default_limit=3)
    d1 = limiter.check("u", "messages", now=_T0)
    assert d1.limit == 3
    assert d1.remaining == 2
    d2 = limiter.check("u", "messages", now=_T0)
    assert d2.remaining == 1
    d3 = limiter.check("u", "messages", now=_T0)
    assert d3.remaining == 0


def test_over_limit_raises_429_with_headers() -> None:
    limiter = RateLimiter(InMemoryRateLimitStore(), default_limit=2)
    limiter.check("u", "messages", now=_T0)
    limiter.check("u", "messages", now=_T0)
    with pytest.raises(RateLimitExceededError) as exc:
        limiter.check("u", "messages", now=_T0)
    ctx = exc.value.context
    assert ctx["limit"] == "2"
    assert ctx["remaining"] == "0"
    assert "reset" in ctx
    assert "retry_after" in ctx


def test_per_endpoint_limits_override_default() -> None:
    limiter = RateLimiter(
        InMemoryRateLimitStore(), default_limit=60, per_endpoint={"messages": 20, "author": 3}
    )
    assert limiter.limit_for("messages") == 20
    assert limiter.limit_for("author") == 3
    assert limiter.limit_for("anything_else") == 60


def test_separate_users_have_separate_buckets() -> None:
    limiter = RateLimiter(InMemoryRateLimitStore(), default_limit=1)
    limiter.check("user_a", "messages", now=_T0)  # a uses its bucket
    # b still has headroom
    d = limiter.check("user_b", "messages", now=_T0)
    assert d.remaining == 0  # b's first (and only) request


def test_window_rolls_over_at_the_next_minute() -> None:
    store = InMemoryRateLimitStore()
    limiter = RateLimiter(store, default_limit=1)
    limiter.check("u", "messages", now=_T0)
    with pytest.raises(RateLimitExceededError):
        limiter.check("u", "messages", now=_T0)
    # next minute → fresh bucket
    next_minute = _T0.replace(minute=1)
    d = limiter.check("u", "messages", now=next_minute)
    assert d.remaining == 0  # first request of the new window


def test_separate_endpoints_have_separate_buckets() -> None:
    limiter = RateLimiter(InMemoryRateLimitStore(), default_limit=1)
    limiter.check("u", "messages", now=_T0)
    # a different endpoint for the same user is independent
    d = limiter.check("u", "runs", now=_T0)
    assert d.remaining == 0

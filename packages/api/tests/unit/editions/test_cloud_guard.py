"""Unit tests for the cloud-edition startup fail-fast (Spec R2, T1).

The headline R2 guard: a misconfigured **cloud** deploy must REFUSE to start
rather than silently ship authless or RLS-bypassing (F-01 + F-06 + F-05). The
guard folds three holes into one fail-fast at the composition root:

  (a) edition is cloud (the explicit signal of intent);
  (b) ``app_database_url`` is set AND not equal to ``database_url`` — else the
      request path runs on the superuser DSN (F-06);
  (c) ``jwt_audience`` is non-empty — else cloud silently skips the aud check (F-05).

Plus a defense-in-depth ``is_superuser`` probe (R2-D-1) that runs against a live
rls_engine checkout: even if the DSNs differ as strings, a privileged role is
refused.

No DB, no network: the config asserts are pure; the probe leg is exercised with
a tiny fake engine that mimics ``engine.connect()`` → ``current_setting``.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
from persona_api.config import APIConfig, Edition
from persona_api.editions import check_cloud_config_guard
from persona_api.errors import CloudConfigRefusedError

if TYPE_CHECKING:
    from collections.abc import Iterator


# A correct cloud config: distinct app DSN (non-superuser role) + an audience.
_GOOD = {
    "edition": Edition.cloud,
    "database_url": "postgresql+psycopg://super@db/persona",
    "app_database_url": "postgresql+psycopg://persona_app@db/persona",
    "jwt_audience": "persona-api",
}


def _cloud(**overrides: object) -> APIConfig:
    """A cloud ``APIConfig`` starting from a correct baseline, with overrides."""
    return APIConfig(**{**_GOOD, **overrides})  # type: ignore[arg-type]


class _FakeConn:
    def __init__(self, is_superuser: str) -> None:
        self._val = is_superuser

    def execute(self, _stmt: object) -> _FakeConn:
        return self

    def scalar(self) -> str:
        return self._val


class _FakeEngine:
    """Mimics the slice of SQLAlchemy ``Engine`` the probe touches."""

    def __init__(self, is_superuser: str) -> None:
        self._val = is_superuser

    @contextmanager
    def connect(self) -> Iterator[_FakeConn]:
        yield _FakeConn(self._val)


# ---------------------------------------------------------------------------
# (a) edition gate — the guard is a no-op for community, fires only for cloud.
# ---------------------------------------------------------------------------


def test_community_is_never_gated() -> None:
    """Community boots byte-unchanged regardless of DSN/audience (zero regression)."""
    check_cloud_config_guard(
        APIConfig(edition=Edition.community, database_url="", app_database_url="", jwt_audience="")
    )


# ---------------------------------------------------------------------------
# (b) F-06 — app DSN must be set AND distinct from the superuser DSN.
# ---------------------------------------------------------------------------


def test_cloud_refuses_when_app_database_url_unset() -> None:
    with pytest.raises(CloudConfigRefusedError):
        check_cloud_config_guard(_cloud(app_database_url=""))


def test_cloud_refuses_when_app_dsn_equals_superuser_dsn() -> None:
    same = "postgresql+psycopg://super@db/persona"
    with pytest.raises(CloudConfigRefusedError):
        check_cloud_config_guard(_cloud(database_url=same, app_database_url=same))


# ---------------------------------------------------------------------------
# (c) F-05 — cloud must force the JWT audience check.
# ---------------------------------------------------------------------------


def test_cloud_refuses_when_jwt_audience_empty() -> None:
    with pytest.raises(CloudConfigRefusedError):
        check_cloud_config_guard(_cloud(jwt_audience=""))


# ---------------------------------------------------------------------------
# The happy path — a fully-correct cloud config passes (no probe engine).
# ---------------------------------------------------------------------------


def test_cloud_passes_with_correct_config() -> None:
    check_cloud_config_guard(_cloud())


# ---------------------------------------------------------------------------
# (probe) R2-D-1 defense-in-depth — is_superuser='on' refuses; 'off' passes.
# ---------------------------------------------------------------------------


def test_cloud_refuses_when_probe_reports_superuser() -> None:
    with pytest.raises(CloudConfigRefusedError):
        check_cloud_config_guard(_cloud(), probe_engine=_FakeEngine("on"))


def test_cloud_passes_when_probe_reports_non_superuser() -> None:
    check_cloud_config_guard(_cloud(), probe_engine=_FakeEngine("off"))


def test_probe_is_skipped_when_no_engine_given() -> None:
    """Config-only call (at ``create_app`` before the engine exists) does not probe."""
    check_cloud_config_guard(_cloud(), probe_engine=None)


# ---------------------------------------------------------------------------
# The refusal carries structured context (domain-exception convention).
# ---------------------------------------------------------------------------


def test_refusal_carries_context() -> None:
    with pytest.raises(CloudConfigRefusedError) as exc_info:
        check_cloud_config_guard(_cloud(app_database_url=""))
    assert exc_info.value.context.get("edition") == "cloud"


# ---------------------------------------------------------------------------
# Wiring: the guard is actually called at create_app (config asserts, pre-engine)
# — proves it is not dead code (mirrors test_create_app_wires_the_gateway_guard).
# ---------------------------------------------------------------------------


def test_create_app_wires_the_cloud_config_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """A cloud boot with APP_DATABASE_URL unset refuses at create_app, before any
    engine is built (the boot crashes — no degradation to a superuser request path)."""
    from persona_api.app import create_app

    # Ensure the gateway guard (which runs after ours) can't pre-empt the assertion.
    monkeypatch.delenv("PERSONA_DOCKER_MCP_GATEWAY_URL", raising=False)
    with pytest.raises(CloudConfigRefusedError):
        create_app(_cloud(app_database_url=""))


def test_build_worker_wires_the_cloud_config_guard() -> None:
    """R2-D-2: the worker composition root REFUSES a misconfigured cloud boot
    (was a soft WARN) — a worker running RLS-bypassing superuser is the same hole."""
    from persona.jobs import JobRegistry
    from persona_api.jobs.worker import build_worker

    with pytest.raises(CloudConfigRefusedError):
        build_worker(_cloud(app_database_url=""), JobRegistry())

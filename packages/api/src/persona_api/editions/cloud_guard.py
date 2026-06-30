"""The cloud-edition startup fail-fast (Spec R2, T1 / R2-D-1, R2-D-2).

The headline R2 hardening: a misconfigured **cloud** deployment must REFUSE to
start rather than silently degrade to an unsafe posture. Three of the audit's
highest-severity findings collapse into one guard, mirroring the existing
:func:`persona_api.editions.guard.check_public_noauth_guard` /
:func:`persona_api.editions.gateway_guard.check_gateway_edition_posture`
precedents (same module, same shape — a pure ``(config) -> None`` that raises a
:class:`persona_api.errors.PersonaError` subclass to refuse):

- **F-01** — ``PERSONA_EDITION`` defaults to ``community`` (no auth wall). The
  public-noauth guard only refuses on a non-loopback bind, so a loopback-fronted
  prod could ship authless. This guard runs *because* edition is cloud and
  enforces that the rest of the cloud config is complete.
- **F-06** — ``effective_app_database_url`` silently falls back to the superuser
  ``database_url`` when ``APP_DATABASE_URL`` is unset; the request path then runs
  RLS-bypassing superuser (cross-tenant collapse). Refuse if ``app_database_url``
  is unset or string-equal to ``database_url``; and, defense-in-depth, probe the
  live rls_engine role and refuse if it is actually a superuser (R2-D-1).
- **F-05** — the JWT ``aud`` check is verified *when configured* but
  ``jwt_audience`` defaults empty with no guard. Cloud must force it.

Community is **never** gated here (zero regression to the zero-infra self-host —
its safety story is the public-bind guard). The probe leg runs only when a live
``probe_engine`` is supplied (inside ``_lifespan``, post-engine-build); the
pure-config asserts run at ``create_app`` before any engine exists (R2-D-1's
two-point wiring). Both run before the app serves a request — fail-fast, never
fail-open.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.logging import get_logger
from sqlalchemy import text

from persona_api.config import Edition
from persona_api.errors import CloudConfigRefusedError

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from persona_api.config import APIConfig

__all__ = ["check_cloud_config_guard"]

_LOG = get_logger("api.editions.cloud_guard")


def _probe_is_superuser(engine: Engine) -> bool:
    """Whether ``engine``'s role connects as a PostgreSQL superuser.

    Reads the read-only ``is_superuser`` GUC on a checkout (``'on'`` / ``'off'``),
    mirroring the Spec 07/19 ``current_setting`` fail-closed idiom (``db/rls.py``).
    A superuser connection bypasses RLS entirely, so this is the last-resort check
    that the request path's role is genuinely non-privileged even when the DSN
    strings differ from ``database_url``.
    """
    with engine.connect() as conn:
        value = conn.execute(text("SELECT current_setting('is_superuser')")).scalar()
    return str(value).strip().lower() == "on"


def check_cloud_config_guard(config: APIConfig, *, probe_engine: Engine | None = None) -> None:
    """Refuse to start a misconfigured ``cloud`` deploy (R2-D-1).

    Called at two composition points with the *same* function (R2-D-1's honest
    two-point wiring): once at ``create_app`` with ``probe_engine=None`` (the
    pure-config asserts, before any engine is built), and again from
    ``_lifespan`` / the worker composition root with the live rls_engine (the
    superuser probe leg). Both run before the process serves work. Idempotent;
    a no-op for the community edition.

    Args:
        config: The API config (its ``edition`` + DSNs + ``jwt_audience`` drive
            the gate).
        probe_engine: The live RLS engine to probe for superuser-ness. ``None``
            skips the probe (the pre-engine ``create_app`` call).

    Raises:
        CloudConfigRefusedError: cloud edition with ``app_database_url`` unset or
            equal to ``database_url`` (F-06), an empty ``jwt_audience`` (F-05), or
            a ``probe_engine`` whose role is a superuser (F-06 defense-in-depth).
    """
    if config.edition is not Edition.cloud:
        return  # community is never gated here — the public-bind guard owns it

    ctx = {"edition": config.edition.value}

    # F-06 (cheap, fail-fast, no DB hit): the request path must use a distinct,
    # non-superuser app DSN — never the superuser ``database_url`` fallback.
    if not config.app_database_url:
        raise CloudConfigRefusedError(
            "refusing to start: PERSONA_EDITION=cloud but APP_DATABASE_URL is unset, so the "
            "request path would fall back to the superuser DATABASE_URL and run RLS-bypassing "
            "(cross-tenant collapse). Set APP_DATABASE_URL to the non-superuser persona_app DSN.",
            context={**ctx, "reason": "app_database_url_unset"},
        )
    if config.app_database_url == config.database_url:
        raise CloudConfigRefusedError(
            "refusing to start: PERSONA_EDITION=cloud but APP_DATABASE_URL equals DATABASE_URL, "
            "so the request path runs on the superuser DSN and RLS is bypassed. Point "
            "APP_DATABASE_URL at the non-superuser persona_app role.",
            context={**ctx, "reason": "app_database_url_equals_superuser"},
        )

    # F-05: cloud must force the JWT audience check (empty silently disables it).
    if not config.jwt_audience:
        raise CloudConfigRefusedError(
            "refusing to start: PERSONA_EDITION=cloud but PERSONA_API_JWT_AUDIENCE is unset, so "
            "the JWT 'aud' claim is not verified. Set PERSONA_API_JWT_AUDIENCE to the expected "
            "audience.",
            context={**ctx, "reason": "jwt_audience_unset"},
        )

    # F-06 defense-in-depth (R2-D-1): even with distinct DSN strings, the role
    # could still be a superuser. Probe the live engine when one is supplied.
    if probe_engine is not None and _probe_is_superuser(probe_engine):
        raise CloudConfigRefusedError(
            "refusing to start: PERSONA_EDITION=cloud but the RLS engine's role is a PostgreSQL "
            "superuser (current_setting('is_superuser')='on'), which bypasses RLS entirely. The "
            "request path must use the non-superuser persona_app role.",
            context={**ctx, "reason": "rls_role_is_superuser"},
        )

    _LOG.debug("cloud-edition config guard passed (edition={edition})", edition=ctx["edition"])

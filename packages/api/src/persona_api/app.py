"""FastAPI application factory (spec 08, T01).

``create_app()`` is the composition root's entry point. It assembles the app,
registers exception handlers (T02), routers (T07+), middleware, and a lifespan
context that owns the long-lived collaborators — the database engine(s), the
``TierRegistry``, and the toolbox/MCP clients (T10 fills the body; on shutdown it
calls ``await tier_registry.aclose()`` + ``await client.disconnect()`` per the
spec-05/06 lifecycle handoff).

The app is stateless (twelve-factor): all persistent state lives in Postgres.
Single uvicorn worker for v0.1 (S08-4 / D-08-5) — the in-memory run event bus
requires it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import FastAPI
from persona_runtime.errors import TierNotConfiguredError
from persona_runtime.tier import tier_registry_from_env

from persona_api.background.run_worker import RunRegistry
from persona_api.config import APIConfig
from persona_api.errors import register_exception_handlers
from persona_api.middleware.rate_limit import (
    InMemoryRateLimitStore,
    PostgresRateLimitStore,
    RateLimiter,
    RateLimitStore,
)
from persona_api.middleware.rls_context import make_rls_engine
from persona_api.routes import conversations, health, me, personas, runs, tools
from persona_api.services import persona_service
from persona_api.services.runtime_factory import RuntimeFactory
from persona_api.services.turn_log_writer import PostgresTurnLogWriter

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy import Engine

__all__ = ["create_app"]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup/shutdown for the long-lived collaborators.

    T05 builds the **RLS engine** here — the per-request engine whose pool
    listener structurally scopes every connection (D-08-1); it is the spine the
    auth/route DB access composes through. T10 extends this with the embedder,
    typed stores, and the ``TierRegistry`` (and tears them down — calling
    ``await tier_registry.aclose()`` + ``await client.disconnect()`` per MCP
    client, D-05-4 / spec-06 handoff).
    """
    config: APIConfig = app.state.config
    rls_engine: Engine | None = None
    if config.effective_app_database_url:
        rls_engine = make_rls_engine(
            config.effective_app_database_url, pool_size=config.db_pool_size
        )
    app.state.rls_engine = rls_engine
    # The embedder for persona memory population (D-08-8). Lazy: weights load on
    # first encode, not at startup. Shared (thread-safe read path).
    app.state.embedder = persona_service.default_embedder(config.embedder_model)
    app.state.audit_root = Path(config.audit_root)
    # Rate limiter (§6, D-08-5). Postgres-backed when a non-RLS engine is
    # available; in-memory otherwise. The buckets table is NOT under RLS, so the
    # Postgres store uses a plain (non-listener) engine.
    app.state.rate_limiter = _build_rate_limiter(config, rls_engine)
    # The agentic-run registry (T11, D-08-5): in-process event bus + task tracker.
    # Single worker (S08-4). Cancelled on shutdown.
    run_registry = RunRegistry(rls_engine) if rls_engine is not None else None
    app.state.run_registry = run_registry

    # Runtime composition root (T10): the TierRegistry (app-scoped) + the
    # per-request loop builders. Built only when a model backend is configured
    # AND a DB engine exists; tests override app.state.build_conversation_loop
    # with a scripted loop, so a missing registry doesn't block them.
    runtime_factory: RuntimeFactory | None = None
    if rls_engine is not None:
        try:
            tier_registry = tier_registry_from_env()
        except TierNotConfiguredError:
            tier_registry = None
        if tier_registry is not None:
            runtime_factory = RuntimeFactory(
                rls_engine=rls_engine,
                embedder=app.state.embedder,
                tier_registry=tier_registry,
                # Postgres turn_logs (D-08-7); RLS-scoped via conversations.
                turn_log_writer=PostgresTurnLogWriter(rls_engine),
                audit_root=Path(config.audit_root),
            )
            app.state.tier_registry = tier_registry
            app.state.authoring_tier = config.authoring_tier
            app.state.build_conversation_loop = runtime_factory.build_conversation_loop
            app.state.build_agentic_loop = runtime_factory.build_agentic_loop
            app.state.title_builder = runtime_factory.build_title  # auto-title (small tier)
    try:
        yield
    finally:
        if run_registry is not None:
            await run_registry.aclose()  # cancel in-flight run tasks (S08-2)
        if runtime_factory is not None:
            await runtime_factory.aclose()  # tier_registry.aclose() + MCP disconnect (D-05-4)
        if rls_engine is not None:
            rls_engine.dispose()


def create_app(config: APIConfig | None = None) -> FastAPI:
    """Build and return the FastAPI application.

    Args:
        config: An :class:`APIConfig`. Defaults to one loaded from the
            environment. Injected in tests to override DSNs/auth knobs.
    """
    config = config or APIConfig()

    app = FastAPI(
        title="Persona API",
        version="0.8.0",
        summary="Hosted service for building and running typed-memory AI personas.",
        lifespan=_lifespan,
    )
    app.state.config = config

    register_exception_handlers(app)

    # Routers are registered as they land (T07 personas, T08 conversations,
    # T11 runs, T12 me/health, T13 tools). Kept as an explicit include list so
    # the surface is visible in one place.
    _register_routers(app)

    return app


def _build_rate_limiter(config: APIConfig, rls_engine: Engine | None) -> RateLimiter:
    """Build the §6 limiter: Postgres-backed when an engine exists + configured,
    else in-memory (dev/tests)."""
    per_endpoint = {
        "messages": config.rate_limit_messages,
        "runs": config.rate_limit_runs,
        "author": config.rate_limit_author,
    }
    store: RateLimitStore
    if config.rate_limit_backend == "postgres" and rls_engine is not None:
        store = PostgresRateLimitStore(rls_engine)
    else:
        store = InMemoryRateLimitStore()
    return RateLimiter(store, default_limit=config.rate_limit_default, per_endpoint=per_endpoint)


def _register_routers(app: FastAPI) -> None:
    """Include all route modules. Extended task-by-task in Phase 5."""
    app.include_router(personas.router)
    app.include_router(conversations.router)
    app.include_router(runs.router)
    app.include_router(me.router)
    app.include_router(health.router)
    app.include_router(tools.router)

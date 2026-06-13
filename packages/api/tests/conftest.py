"""Shared test fixtures for persona-api.

The api test tree has NO ``__init__.py`` (spec-05 finding #1 — avoids a
``tests.conftest`` module-name collision across packages). Shared fakes/fixtures
live here.

Integration tests need a real Postgres 16 + pgvector. They read ``DATABASE_URL``
(sync psycopg3 dialect, ``postgresql+psycopg://``) and skip if it is unset or the
server is unreachable — CI sets it to a Docker service; locally:

    docker compose up -d postgres
    export DATABASE_URL=postgresql+psycopg://persona:persona@localhost:5432/persona
    uv run pytest -m integration
"""

from __future__ import annotations

import hashlib
import math
import os
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from sqlalchemy import Engine


class HashEmbedder384:
    """Deterministic 384-dim L2-normalised embedder for Postgres tests.

    Mirrors ``packages/core/tests/_embedder.py``'s HashEmbedder but at the
    production vector(384) dimension (the core fake is 32-dim, which the
    Postgres column rejects). SHA-256-derived, so the same text always maps to
    the same vector — lets decay/recall tests reason about ranking.
    """

    model_name: str = "test-hash-embedder-384"
    dimension: int = 384

    def encode(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            # Derive floats from digest BYTES (0..255 → -0.5..0.5). Never NaN
            # (unlike reinterpreting raw bytes as IEEE-754 floats, which can
            # land on NaN/inf bit patterns that pgvector rejects).
            byts: list[int] = []
            counter = 0
            while len(byts) < self.dimension:
                byts.extend(hashlib.sha256(f"{text}:{counter}".encode()).digest())
                counter += 1
            vec = [(b / 255.0) - 0.5 for b in byts[: self.dimension]]
            norm = math.sqrt(sum(x * x for x in vec)) or 1.0
            out.append([x / norm for x in vec])
        return out


@pytest.fixture
def embedder() -> HashEmbedder384:
    return HashEmbedder384()


def _database_url() -> str | None:
    return os.environ.get("DATABASE_URL")


@pytest.fixture(scope="session")
def database_url() -> str:
    """The sync Postgres DSN, or skip the test if unavailable."""
    url = _database_url()
    if not url:
        pytest.skip("DATABASE_URL not set; skipping Postgres integration test")
    if "+asyncpg" in url:
        # The transport is sync (D-07-1); coerce a stray async DSN.
        url = url.replace("+asyncpg", "+psycopg")
    return url


@pytest.fixture
def pg_engine(database_url: str) -> Iterator[Engine]:
    """A sync SQLAlchemy engine on a freshly-built schema (tables only).

    Drops and recreates all tables (via the Core ``MetaData``) so each test
    starts clean. This builds TABLES but NOT the RLS policies — store/CRUD/decay
    tests don't need RLS (they run as superuser). RLS-isolation tests use
    :func:`migrated_engine` instead, which runs the real Alembic migration so
    the policies exist.
    """
    from persona_api.db import metadata
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
            conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            metadata.create_all(conn)
    except OperationalError as exc:
        pytest.skip(f"Postgres unreachable at DATABASE_URL: {exc}")
    yield engine
    engine.dispose()


@pytest.fixture
def migrated_engine(database_url: str) -> Iterator[Engine]:
    """A superuser engine on a schema built by the real Alembic migration.

    Unlike :func:`pg_engine` (tables only), this runs ``alembic upgrade head``
    so RLS ENABLE/FORCE + policies are present — required for the RLS-isolation
    tests. It also (re-)grants table privileges to the non-superuser
    ``persona_app`` role if that role exists, since the schema is rebuilt each
    test.
    """
    from pathlib import Path

    from alembic import command
    from alembic.config import Config
    from sqlalchemy import create_engine, text
    from sqlalchemy.exc import OperationalError

    engine = create_engine(database_url)
    api_dir = Path(__file__).resolve().parents[1]
    try:
        with engine.begin() as conn:
            conn.execute(text("DROP SCHEMA public CASCADE"))
            conn.execute(text("CREATE SCHEMA public"))
        cfg = Config(str(api_dir / "alembic.ini"))
        cfg.set_main_option("script_location", str(api_dir / "alembic"))
        cfg.set_main_option("sqlalchemy.url", database_url)
        command.upgrade(cfg, "head")
        with engine.begin() as conn:
            if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'persona_app'")).first():
                conn.execute(text("GRANT USAGE ON SCHEMA public TO persona_app"))
                conn.execute(
                    text(
                        "GRANT SELECT, INSERT, UPDATE, DELETE "
                        "ON ALL TABLES IN SCHEMA public TO persona_app"
                    )
                )
    except OperationalError as exc:
        pytest.skip(f"Postgres unreachable at DATABASE_URL: {exc}")
    yield engine
    engine.dispose()

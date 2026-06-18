"""Community-edition zero-infra boot (Spec 33, Cluster B keystone, half 2).

Proves the "clone → set a model key → run" promise without Postgres/Docker:
``create_app`` under ``PERSONA_EDITION=community`` boots on SQLite + Chroma, seeds
the single local owner, serves requests with NO auth wall, and the relational
store works through a real route — all in a temp dir, no external services.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from persona_api.app import create_app
from persona_api.config import APIConfig, Edition

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def community_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    # No DATABASE_URL, no model key, no Clerk — pure zero-infra community boot.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_DATABASE_URL", raising=False)
    config = APIConfig(
        edition=Edition.community,
        community_db_path=tmp_path / "community.db",
        community_memory_path=tmp_path / "chroma",
        workspace_root=tmp_path / "work",
        audit_root=str(tmp_path / "audit"),
    )
    app = create_app(config)
    with TestClient(app) as client:  # runs the lifespan (SQLite schema-create + ensure_owner)
        yield client


def test_community_boots_on_sqlite_with_no_postgres(community_client: TestClient) -> None:
    # The relational store is a SQLite file; no Postgres engine, no admin engine.
    assert community_client.app.state.rls_engine is not None
    assert community_client.app.state.admin_engine is None
    assert str(community_client.app.state.rls_engine.url).startswith("sqlite")


def test_community_credits_endpoint_needs_no_auth_and_is_unlimited(
    community_client: TestClient,
) -> None:
    # No Authorization header — community has no auth wall.
    resp = community_client.get("/v1/me/credits")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["balance"] > 0
    assert body["low_balance"] is False


def test_community_relational_store_works_through_a_route(community_client: TestClient) -> None:
    # The personas list route runs a real SELECT against the SQLite store under
    # the seeded local owner; a fresh DB returns an empty list (not an error).
    resp = community_client.get("/v1/personas")
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


def test_community_owner_is_seeded(community_client: TestClient) -> None:
    from persona_api.db.community import build_community_metadata
    from sqlalchemy import select

    users = build_community_metadata().tables["users"]
    engine = community_client.app.state.rls_engine
    with engine.connect() as conn:
        ids = conn.execute(select(users.c.id)).scalars().all()
    assert "local-owner" in ids

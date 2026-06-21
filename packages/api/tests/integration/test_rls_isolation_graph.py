"""Adversarial RLS isolation for the knowledge-graph tables (Spec K0, T4; crit 6).

Mirrors ``test_rls_isolation.py``: seed two tenants' graph rows as superuser, then
query under each tenant's RLS context as the NON-SUPERUSER ``persona_app`` role
and assert ZERO cross-tenant rows on graph_nodes / graph_edges / graph_entities.
Also asserts fail-closed: an unset ``app.current_user_id`` GUC → zero rows.

The graph uses the DIRECT ``owner_id`` policy (per *user*, not the persona
FK-chain). Superusers bypass RLS, so the test MUST connect as ``persona_app``
(``APP_DATABASE_URL``); it skips if that role DSN is unset.
"""

# ruff: noqa: ANN401, ARG001
from __future__ import annotations

import os

import pytest
from persona_api.db.engine import rls_connection
from sqlalchemy import create_engine, text

pytestmark = pytest.mark.integration

_GRAPH_TABLES = ("graph_nodes", "graph_edges", "graph_entities", "graph_node_entities")
_ZERO_VEC = "[" + ",".join(["0"] * 384) + "]"


@pytest.fixture
def app_engine(migrated_engine: object) -> object:
    """Non-superuser ``persona_app`` engine (depends on migrated_engine for grants)."""
    app_url = os.environ.get("APP_DATABASE_URL")
    if not app_url:
        pytest.skip("APP_DATABASE_URL (non-superuser role) not set; skipping graph RLS test")
    return create_engine(app_url.replace("+asyncpg", "+psycopg"))


def _seed_two_tenants(superuser_engine: object) -> None:
    with superuser_engine.begin() as conn:  # type: ignore[attr-defined]
        conn.execute(
            text(
                "INSERT INTO users (id, email) VALUES "
                "('user_a','a@example.com'),('user_b','b@example.com')"
            )
        )
        # Two nodes per tenant (so an intra-tenant edge has both endpoints).
        nodes = (("na1", "user_a"), ("na2", "user_a"), ("nb1", "user_b"), ("nb2", "user_b"))
        for nid, owner in nodes:
            conn.execute(
                text(
                    "INSERT INTO graph_nodes "
                    "(id, owner_id, node_kind, concept_name, content, metadata, embedding, "
                    " embedding_model, content_hash, provenance, created_at) VALUES "
                    f"(:id, :owner, 'fact', 'c', 'c', '{{}}', '{_ZERO_VEC}', 'm', 'h', '[]', now())"
                ),
                {"id": nid, "owner": owner},
            )
        edges = (("ea", "user_a", "na1", "na2"), ("eb", "user_b", "nb1", "nb2"))
        for eid, owner, src, dst in edges:
            conn.execute(
                text(
                    "INSERT INTO graph_edges "
                    "(id, owner_id, src_node_id, dst_node_id, link_type, created_at) VALUES "
                    "(:id, :owner, :src, :dst, 'semantic', now())"
                ),
                {"id": eid, "owner": owner, "src": src, "dst": dst},
            )
        for entid, owner in (("entA", "user_a"), ("entB", "user_b")):
            conn.execute(
                text(
                    "INSERT INTO graph_entities "
                    "(id, owner_id, canonical_name, aliases, name_embedding, created_at) VALUES "
                    f"(:id, :owner, 'E', '[]', '{_ZERO_VEC}', now())"
                ),
                {"id": entid, "owner": owner},
            )
        for owner, nid, entid in (("user_a", "na1", "entA"), ("user_b", "nb1", "entB")):
            conn.execute(
                text(
                    "INSERT INTO graph_node_entities (owner_id, node_id, entity_id, created_at) "
                    "VALUES (:owner, :nid, :entid, now())"
                ),
                {"owner": owner, "nid": nid, "entid": entid},
            )


@pytest.mark.parametrize("table", _GRAPH_TABLES)
def test_graph_tables_isolated_per_tenant(
    migrated_engine: object, app_engine: object, table: str
) -> None:
    _seed_two_tenants(migrated_engine)
    with rls_connection(app_engine, "user_a") as conn:  # type: ignore[arg-type]
        owners = {r[0] for r in conn.execute(text(f"SELECT owner_id FROM {table}"))}  # noqa: S608
    assert owners == {"user_a"}, f"RLS leak on {table}: user_a saw {owners}"


@pytest.mark.parametrize("table", _GRAPH_TABLES)
def test_graph_tables_fail_closed_when_user_unset(
    migrated_engine: object, app_engine: object, table: str
) -> None:
    # No set_current_user → current_setting(...,true) NULL → zero rows.
    _seed_two_tenants(migrated_engine)
    with app_engine.begin() as conn:  # type: ignore[attr-defined]
        rows = conn.execute(text(f"SELECT owner_id FROM {table}")).all()  # noqa: S608
    assert rows == [], f"{table} must fail closed when app.current_user_id is unset"


def test_graph_cross_tenant_write_blocked_by_with_check(
    migrated_engine: object, app_engine: object
) -> None:
    # WITH CHECK must stop user_a from inserting a node owned by user_b.
    _seed_two_tenants(migrated_engine)
    from sqlalchemy.exc import ProgrammingError

    with (
        rls_connection(app_engine, "user_a") as conn,  # type: ignore[arg-type]
        pytest.raises(ProgrammingError),
    ):
        conn.execute(
            text(
                "INSERT INTO graph_nodes "
                "(id, owner_id, node_kind, concept_name, content, metadata, embedding, "
                " embedding_model, content_hash, provenance, created_at) VALUES "
                f"('evil','user_b','fact','c','c','{{}}','{_ZERO_VEC}','m','h','[]', now())"
            )
        )

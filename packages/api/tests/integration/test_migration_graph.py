"""Migration 011 (knowledge graph) creates tables + indexes + RLS (Spec K0, T4).

Mirrors ``test_migration.py``: a clean ``alembic upgrade head`` builds the three
graph tables with their indexes and RLS (ENABLE + FORCE + ``user_isolation``
policy); ``011``'s downgrade drops only the graph tables, leaving the rest intact.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

pytestmark = pytest.mark.integration

_API_DIR = Path(__file__).resolve().parents[2]  # packages/api
_GRAPH_TABLES = {"graph_nodes", "graph_edges", "graph_entities", "graph_node_entities"}


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(_API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _grant_persona_app(database_url: str) -> None:
    """Re-grant the non-superuser ``persona_app`` role on the freshly-built schema.

    This file rebuilds ``public`` from scratch (DROP SCHEMA + raw ``alembic
    upgrade head``), which restores the tables/RLS but NOT the role grants that
    ``conftest._migrate_to_head`` applies at session start. When this file is no
    longer the LAST shared-schema consumer in a run (e.g. an A1 schema test runs
    first, so the session is already migrated, then a ``persona_app``-driven RLS
    test runs AFTER this rebuild), the conftest's ``_schema_is_at_head`` sees the
    schema at head and skips a re-migrate — so without re-granting here, that next
    test sees every table as ``relation … does not exist`` (Postgres masks a
    missing schema-USAGE grant as a missing relation). Mirror the conftest grant.
    """
    engine = create_engine(database_url)
    try:
        with engine.begin() as conn:
            if conn.execute(text("SELECT 1 FROM pg_roles WHERE rolname = 'persona_app'")).first():
                conn.execute(text("GRANT USAGE ON SCHEMA public TO persona_app"))
                conn.execute(
                    text(
                        "GRANT SELECT, INSERT, UPDATE, DELETE "
                        "ON ALL TABLES IN SCHEMA public TO persona_app"
                    )
                )
    finally:
        engine.dispose()


def test_migration_creates_graph_tables_indexes_and_rls(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()

    command.upgrade(_alembic_config(database_url), "head")

    engine = create_engine(database_url)
    insp = inspect(engine)
    assert _GRAPH_TABLES.issubset(set(insp.get_table_names()))

    node_idx = {i["name"] for i in insp.get_indexes("graph_nodes")}
    assert {
        "ix_graph_nodes_embedding_hnsw",
        "ix_graph_nodes_fts",
        "ix_graph_nodes_owner",
    } <= node_idx
    edge_idx = {i["name"] for i in insp.get_indexes("graph_edges")}
    assert {"ix_graph_edges_src", "ix_graph_edges_dst"} <= edge_idx
    ent_idx = {i["name"] for i in insp.get_indexes("graph_entities")}
    assert {"ix_graph_entities_name_hnsw", "ix_graph_entities_owner"} <= ent_idx

    with engine.connect() as conn:
        forced = {
            r[0]
            for r in conn.execute(
                text("SELECT relname FROM pg_class WHERE relrowsecurity AND relforcerowsecurity")
            )
        }
        policied = {
            r[0]
            for r in conn.execute(
                text("SELECT tablename FROM pg_policies WHERE policyname = 'user_isolation'")
            )
        }
    assert forced >= _GRAPH_TABLES
    assert policied >= _GRAPH_TABLES
    engine.dispose()
    # This rebuild left a grant-less schema; re-grant so a persona_app RLS test
    # running after this one (when the session is already migrated) still sees the
    # tables. See _grant_persona_app.
    _grant_persona_app(database_url)


def test_graph_migration_downgrade_drops_only_graph(database_url: str) -> None:
    cfg = _alembic_config(database_url)
    command.upgrade(cfg, "head")
    # Downgrade just migration 011 → graph tables gone, everything else intact.
    command.downgrade(cfg, "010_add_message_tier")
    engine = create_engine(database_url)
    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert tables.isdisjoint(_GRAPH_TABLES)
    assert {"users", "personas", "memory_chunks"}.issubset(tables)  # spec-07 tables survive
    engine.dispose()
    command.upgrade(cfg, "head")  # leave migrated for later session tests
    _grant_persona_app(database_url)  # …with the persona_app grants restored too

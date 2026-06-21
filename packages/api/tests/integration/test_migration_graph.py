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

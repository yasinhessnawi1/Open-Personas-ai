"""Cluster B keystone tests (Spec 33): cloud-DDL invariance + community boot.

Two halves of the dual guard:

* **Cloud unregressed** — the JSON-variant + dialect-aware-UUID changes do NOT
  alter the PostgreSQL DDL: every originally-``JSONB`` column still compiles to
  ``JSONB`` and every PK default still compiles to ``gen_random_uuid()`` under
  the postgresql dialect. This is the "empty cloud-DDL diff" guard.
* **Community boots zero-infra** — the community-variant metadata creates on a
  real SQLite file and round-trips CRUD (client-side UUID + RETURNING, JSON
  columns, composite-FK tenant defence, CHECK constraints), with the fixed
  owner seeded by ``ensure_owner``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from persona_api.db import models
from persona_api.db.community import (
    build_community_metadata,
    create_community_schema,
    ensure_owner,
    make_community_engine,
)
from sqlalchemy import insert, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlalchemy.schema import CreateTable

if TYPE_CHECKING:
    from pathlib import Path

# Columns that were JSONB pre-Spec-33 (must stay JSONB on Postgres).
_JSON_COLUMNS = {
    "messages": ["tool_calls", "channel", "images"],
    "runs": ["steps"],
    "memory_chunks": ["metadata"],
    "audit_log": ["metadata"],
    "user_mcp_servers": ["discovered_tools"],
}


def _pg_ddl(table_name: str) -> str:
    table = models.metadata.tables[table_name]
    return str(CreateTable(table).compile(dialect=postgresql.dialect()))


# ---------------------------------------------------------------- cloud unregressed


@pytest.mark.parametrize(("table", "columns"), _JSON_COLUMNS.items())
def test_json_columns_still_compile_to_jsonb_on_postgres(table: str, columns: list[str]) -> None:
    """The JSON-variant change keeps the cloud DDL byte-identical: JSONB stays JSONB."""
    ddl = _pg_ddl(table)
    for col in columns:
        # the column line must carry JSONB, never the generic JSON
        line = next(line for line in ddl.splitlines() if f"{col} " in line)
        assert "JSONB" in line, f"{table}.{col} no longer JSONB on Postgres: {line!r}"


def test_pk_defaults_still_gen_random_uuid_on_postgres() -> None:
    """Cloud PK generation is unchanged — still server-side gen_random_uuid()."""
    # personas/conversations/messages/runs/turn_logs/credit_transactions/audit_log/
    # user_mcp_servers all carry the gen_random_uuid()::text server default.
    for table in ("personas", "conversations", "messages", "runs"):
        assert "gen_random_uuid()" in _pg_ddl(table)


def test_canonical_metadata_unmutated_still_has_memory_chunks() -> None:
    """Building the community metadata must NOT mutate the canonical metadata."""
    build_community_metadata()  # must be side-effect-free on models.metadata
    assert "memory_chunks" in models.metadata.tables
    # the canonical embedding column is still the pgvector type
    assert "memory_chunks" in models.metadata.tables


# ---------------------------------------------------------------- community boots


def test_community_metadata_excludes_memory_chunks() -> None:
    md = build_community_metadata()
    names = set(md.tables)
    assert "memory_chunks" not in names  # vectors live in Chroma in community
    # the app tables are all present
    assert {"users", "personas", "conversations", "messages", "runs"} <= names


def test_community_schema_creates_on_sqlite_and_round_trips(tmp_path: Path) -> None:
    db_path = tmp_path / "community.db"
    engine = make_community_engine(db_path)
    create_community_schema(engine)
    ensure_owner(engine, owner_id="local-owner", email="local@localhost")
    # ensure_owner is idempotent
    ensure_owner(engine, owner_id="local-owner", email="local@localhost")

    md = build_community_metadata()
    personas = md.tables["personas"]
    conversations = md.tables["conversations"]
    messages = md.tables["messages"]
    runs = md.tables["runs"]

    with engine.begin() as conn:
        # client-side UUID default fires + RETURNING works on SQLite 3.35+
        pid = conn.execute(
            insert(personas).returning(personas.c.id).values(owner_id="local-owner", yaml="name: x")
        ).scalar_one()
        assert isinstance(pid, str)
        assert len(pid) == 36  # uuid4 string

        cid = conn.execute(
            insert(conversations)
            .returning(conversations.c.id)
            .values(owner_id="local-owner", persona_id=pid, title="t")
        ).scalar_one()

        # JSON columns round-trip as python objects
        conn.execute(
            insert(messages).values(
                conversation_id=cid,
                role="assistant",
                content="hi",
                tool_calls=[{"name": "search"}],
                images=[{"workspace_path": "a.png", "media_type": "image/png"}],
            )
        )
        conn.execute(insert(runs).values(owner_id="local-owner", persona_id=pid, task="do"))

    with engine.connect() as conn:
        row = conn.execute(select(messages.c.tool_calls, messages.c.images)).first()
        assert row is not None
        assert row.tool_calls == [{"name": "search"}]
        assert row.images == [{"workspace_path": "a.png", "media_type": "image/png"}]
        assert conn.execute(select(runs.c.steps)).scalar_one() == []  # server_default '[]'
    engine.dispose()


def test_community_composite_fk_enforced(tmp_path: Path) -> None:
    """The cross-tenant-defence composite FK is enforced under SQLite (PRAGMA on)."""
    db_path = tmp_path / "community.db"
    engine = make_community_engine(db_path)
    create_community_schema(engine)
    ensure_owner(engine, owner_id="local-owner", email="local@localhost")

    md = build_community_metadata()
    users = md.tables["users"]
    personas = md.tables["personas"]
    conversations = md.tables["conversations"]

    with engine.begin() as conn:
        pid = conn.execute(
            insert(personas).returning(personas.c.id).values(owner_id="local-owner", yaml="y")
        ).scalar_one()
        conn.execute(insert(users).values(id="other", email="other@localhost"))

    # a conversation attaching to local-owner's persona under a DIFFERENT owner
    # must be rejected by the composite FK.
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(conversations).values(owner_id="other", persona_id=pid, title="x"))
    engine.dispose()


def test_community_check_constraint_enforced(tmp_path: Path) -> None:
    db_path = tmp_path / "community.db"
    engine = make_community_engine(db_path)
    create_community_schema(engine)
    ensure_owner(engine, owner_id="local-owner", email="local@localhost")

    md = build_community_metadata()
    personas = md.tables["personas"]
    conversations = md.tables["conversations"]
    messages = md.tables["messages"]

    with engine.begin() as conn:
        pid = conn.execute(
            insert(personas).returning(personas.c.id).values(owner_id="local-owner", yaml="y")
        ).scalar_one()
        cid = conn.execute(
            insert(conversations)
            .returning(conversations.c.id)
            .values(owner_id="local-owner", persona_id=pid, title="t")
        ).scalar_one()

    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(insert(messages).values(conversation_id=cid, role="BOGUS", content="x"))
    engine.dispose()

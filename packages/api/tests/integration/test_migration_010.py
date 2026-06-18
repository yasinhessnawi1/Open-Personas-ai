"""Migration 010 (messages.tier_used) round-trip test (Spec 35, D-35-2).

Proves the per-message tier-persistence column: ``messages.tier_used`` is present
+ nullable at ``head``, an assistant row round-trips its tier (``small`` /
``mid`` / ``frontier``), the historical / non-assistant path stores NULL (the
"no chip, never a wrong tier" degrade), and ``downgrade`` removes it. Mirrors the
migration-002 programmatic Alembic pattern (cwd-independent).

Split-home note: ``001_initial`` is left UNTOUCHED; it builds the schema via
``metadata.create_all`` from the current canonical models, which now declare
``tier_used`` — so on a fresh DB the column already exists after ``001`` and
``010``'s ``ADD COLUMN IF NOT EXISTS`` is an idempotent no-op. ``010`` is the
migration of record; the guard keeps it correct without modifying ``001``.

Each test resets the schema at the start AND end so the shared integration DB is
left clean for other migration tests (no leftover ``alembic_version``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = pytest.mark.integration

_API_DIR = Path(__file__).resolve().parents[2]  # packages/api
_ALEMBIC_INI = _API_DIR / "alembic.ini"


def _alembic_config(database_url: str) -> Config:
    cfg = Config(str(_ALEMBIC_INI))
    cfg.set_main_option("script_location", str(_API_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def _reset_schema(database_url: str) -> None:
    engine = create_engine(database_url)
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    engine.dispose()


def _message_columns(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("messages")}
    finally:
        engine.dispose()


@pytest.fixture
def clean_db(database_url: str) -> Iterator[str]:
    """Reset the schema before and after so migration tests don't contaminate
    each other on the shared integration DB (no leftover alembic_version)."""
    _reset_schema(database_url)
    yield database_url
    _reset_schema(database_url)


def test_010_adds_and_removes_tier_used_column(clean_db: str) -> None:
    cfg = _alembic_config(clean_db)

    # head: tier_used present, nullable.
    command.upgrade(cfg, "head")
    assert "tier_used" in _message_columns(clean_db)
    engine = create_engine(clean_db)
    try:
        col = next(c for c in inspect(engine).get_columns("messages") if c["name"] == "tier_used")
        assert col["nullable"] is True
    finally:
        engine.dispose()

    # downgrade 010 -> 009: the column is dropped.
    command.downgrade(cfg, "009_user_mcp_servers")
    assert "tier_used" not in _message_columns(clean_db)


def test_tier_used_round_trips_on_assistant_and_is_null_otherwise(clean_db: str) -> None:
    """The assistant row stores its tier; the user row (and any pre-010 row)
    stores NULL — the per-message chip degrades to 'no chip', never a wrong tier."""
    cfg = _alembic_config(clean_db)
    command.upgrade(cfg, "head")

    engine = create_engine(clean_db)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, email) VALUES ('u_010', 'u010@x.test')"))
            conn.execute(
                text("INSERT INTO personas (id, owner_id, yaml) VALUES ('p_010', 'u_010', 'y')")
            )
            conn.execute(
                text(
                    "INSERT INTO conversations (id, owner_id, persona_id) "
                    "VALUES ('c_010', 'u_010', 'p_010')"
                )
            )
            # assistant row carries the tier; user row carries NULL.
            conn.execute(
                text(
                    "INSERT INTO messages (id, conversation_id, role, content, tier_used) "
                    "VALUES ('m_010a', 'c_010', 'assistant', 'hello', 'frontier')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO messages (id, conversation_id, role, content) "
                    "VALUES ('m_010u', 'c_010', 'user', 'hi')"
                )
            )
        with engine.begin() as conn:
            tier = conn.execute(
                text("SELECT tier_used FROM messages WHERE id = 'm_010a'")
            ).scalar_one()
            user_tier = conn.execute(
                text("SELECT tier_used FROM messages WHERE id = 'm_010u'")
            ).scalar_one()
        assert tier == "frontier"
        assert user_tier is None
    finally:
        engine.dispose()

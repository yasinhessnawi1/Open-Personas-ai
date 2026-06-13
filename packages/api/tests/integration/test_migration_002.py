"""Migration 002 (messages.channel) round-trip test (spec 08, T04, D-08-3).

Proves the first incremental migration: the nullable ``messages.channel`` JSONB
column is present + nullable at ``head``, the column round-trips a connector-shaped
value (and the null-channel web-UI path stores NULL), and ``downgrade`` removes it.
Mirrors the spec-07 programmatic Alembic pattern (cwd-independent).

Split-home note: ``001_initial`` is left UNTOUCHED (spec 07); it builds the schema
via ``metadata.create_all`` from the *current* canonical models, which now declare
``channel`` — so on a fresh DB the column already exists after ``001`` and ``002``'s
``ADD COLUMN IF NOT EXISTS`` is an idempotent no-op. ``002`` is the migration of
record; the guard keeps it correct without modifying ``001``. The test therefore
does NOT assert anything about the impure intermediate "001 only" state — it asserts
``002``'s guarantees: present+nullable at head, round-trips, gone after downgrade.

Each test resets the schema at the start AND end so the shared integration DB is
left clean for other migration tests in the session (no leftover
``alembic_version``).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import bindparam, create_engine, inspect, text
from sqlalchemy.dialects.postgresql import JSONB

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


def test_002_adds_and_removes_channel_column(clean_db: str) -> None:
    cfg = _alembic_config(clean_db)

    # head (001 create_all + 002 idempotent guard): channel present, nullable.
    command.upgrade(cfg, "head")
    assert "channel" in _message_columns(clean_db)
    engine = create_engine(clean_db)
    try:
        channel_col = next(
            c for c in inspect(engine).get_columns("messages") if c["name"] == "channel"
        )
        assert channel_col["nullable"] is True
    finally:
        engine.dispose()

    # downgrade 002 -> 001: 002's downgrade drops the column.
    command.downgrade(cfg, "001_initial")
    assert "channel" not in _message_columns(clean_db)


def test_channel_column_round_trips_a_value(clean_db: str) -> None:
    """A connector-shaped JSONB value stores and reads back; the null-channel
    (web-UI) path stores NULL."""
    cfg = _alembic_config(clean_db)
    command.upgrade(cfg, "head")

    engine = create_engine(clean_db)
    channel = {
        "platform": "telegram",
        "platform_user_id": "12345",
        "platform_chat_id": "67890",
        "metadata": {"k": "v"},
    }
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, email) VALUES ('u_002', 'u002@x.test')"))
            conn.execute(
                text("INSERT INTO personas (id, owner_id, yaml) VALUES ('p_002', 'u_002', 'y')")
            )
            conn.execute(
                text(
                    "INSERT INTO conversations (id, owner_id, persona_id) "
                    "VALUES ('c_002', 'u_002', 'p_002')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO messages (id, conversation_id, role, content, channel) "
                    "VALUES ('m_002', 'c_002', 'user', 'hi', :ch)"
                ).bindparams(bindparam("ch", value=channel, type_=JSONB)),
            )
        with engine.begin() as conn:
            row = conn.execute(text("SELECT channel FROM messages WHERE id = 'm_002'")).scalar_one()
            # null-channel path: a second message with NULL channel (the web-UI case)
            conn.execute(
                text(
                    "INSERT INTO messages (id, conversation_id, role, content) "
                    "VALUES ('m_002b', 'c_002', 'assistant', 'hello')"
                )
            )
            null_row = conn.execute(
                text("SELECT channel FROM messages WHERE id = 'm_002b'")
            ).scalar_one()
        assert row == channel
        assert null_row is None
    finally:
        engine.dispose()

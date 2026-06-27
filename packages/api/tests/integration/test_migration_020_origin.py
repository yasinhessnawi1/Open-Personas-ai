"""Migration 020 (conversations.origin) round-trip test (Spec V9, V9-D-3).

Proves the conversation **origin marker** — the single shared `chat | call`
attribute that is the ONLY seam between chat and voice (V9-D-3). At `head` the
column is present, NOT NULL, defaults to `'chat'`, and a CHECK rejects any value
outside `{chat, call}`. The load-bearing operational property is the **explicit
backfill** (V9-D-X-migration / the T1 carry-item): a conversation that existed
*before* this migration — i.e. every pre-V9 row — reads `'chat'` afterwards (all
pre-V9 conversations are chat-born). `downgrade` removes the column + CHECK.

Mirrors the migration-010 programmatic Alembic pattern (cwd-independent). Each
test resets the schema at start AND end so the shared integration DB is left
clean for other migration tests (no leftover ``alembic_version``).

Split-home note: ``001_initial`` is left UNTOUCHED; it builds the schema via
``metadata.create_all`` from the canonical models, which now declare ``origin``
+ the CHECK — so on a fresh DB the column already exists after ``001`` and
``020``'s guarded ``ADD COLUMN IF NOT EXISTS`` / ``SET NOT NULL`` is an
idempotent no-op. ``020`` is the migration of record.
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


def _conversation_columns(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("conversations")}
    finally:
        engine.dispose()


@pytest.fixture
def clean_db(database_url: str) -> Iterator[str]:
    """Reset the schema before and after so migration tests don't contaminate
    each other on the shared integration DB (no leftover alembic_version)."""
    _reset_schema(database_url)
    yield database_url
    _reset_schema(database_url)


def test_020_adds_and_removes_origin_column(clean_db: str) -> None:
    cfg = _alembic_config(clean_db)

    # head: origin present, NOT NULL.
    command.upgrade(cfg, "head")
    assert "origin" in _conversation_columns(clean_db)
    engine = create_engine(clean_db)
    try:
        col = next(c for c in inspect(engine).get_columns("conversations") if c["name"] == "origin")
        assert col["nullable"] is False
    finally:
        engine.dispose()

    # downgrade origin (020) -> its predecessor 019_task_model: the column is
    # dropped (this also unwinds 021_add_calls_table, which sits above origin).
    command.downgrade(cfg, "019_task_model")
    assert "origin" not in _conversation_columns(clean_db)


def test_origin_defaults_to_chat_and_check_rejects_unknown(clean_db: str) -> None:
    """A row written without ``origin`` defaults to ``'chat'``; ``'call'`` is
    accepted; anything else is rejected by the CHECK (the seam is closed)."""
    cfg = _alembic_config(clean_db)
    command.upgrade(cfg, "head")

    engine = create_engine(clean_db)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, email) VALUES ('u_019', 'u019@x.test')"))
            conn.execute(
                text("INSERT INTO personas (id, owner_id, yaml) VALUES ('p_019', 'u_019', 'y')")
            )
            # no origin given -> server default 'chat'
            conn.execute(
                text(
                    "INSERT INTO conversations (id, owner_id, persona_id) "
                    "VALUES ('c_chat', 'u_019', 'p_019')"
                )
            )
            # explicit 'call' is accepted
            conn.execute(
                text(
                    "INSERT INTO conversations (id, owner_id, persona_id, origin) "
                    "VALUES ('c_call', 'u_019', 'p_019', 'call')"
                )
            )
        with engine.begin() as conn:
            chat_origin = conn.execute(
                text("SELECT origin FROM conversations WHERE id = 'c_chat'")
            ).scalar_one()
            call_origin = conn.execute(
                text("SELECT origin FROM conversations WHERE id = 'c_call'")
            ).scalar_one()
        assert chat_origin == "chat"
        assert call_origin == "call"

        # the CHECK rejects an out-of-vocabulary origin.
        with pytest.raises(Exception, match="conversations_origin_check"), engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO conversations (id, owner_id, persona_id, origin) "
                    "VALUES ('c_bad', 'u_019', 'p_019', 'sms')"
                )
            )
    finally:
        engine.dispose()


def test_existing_rows_backfill_to_chat(clean_db: str) -> None:
    """The T1 load-bearing property: a conversation that exists BEFORE the origin
    column reads ``'chat'`` afterwards (all pre-V9 conversations are chat-born).

    This is the genuine DEPLOYED-DB path — a real Postgres that has the
    conversations table but NOT yet the ``origin`` column. The split-home harness
    can't reach that state by stopping at 018 (``001_initial`` builds the schema
    via ``metadata.create_all`` from the *current* canonical models, which already
    declare ``origin``), so we reproduce it faithfully: upgrade to the origin
    migration's predecessor (019_task_model), then DROP the column + its CHECK and
    rewind ``alembic_version`` to 019_task_model, insert a pre-existing row, and run
    020 — asserting its explicit UPDATE backfill pins the orphan row to ``'chat'``.
    """
    cfg = _alembic_config(clean_db)
    command.upgrade(cfg, "019_task_model")

    engine = create_engine(clean_db)
    try:
        with engine.begin() as conn:
            # Simulate the real pre-origin deployed schema: no origin column.
            conn.execute(
                text(
                    "ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_origin_check"
                )
            )
            conn.execute(text("ALTER TABLE conversations DROP COLUMN IF EXISTS origin"))
            conn.execute(text("UPDATE alembic_version SET version_num = '019_task_model'"))
        assert "origin" not in _conversation_columns(clean_db)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, email) VALUES ('u_bf', 'ubf@x.test')"))
            conn.execute(
                text("INSERT INTO personas (id, owner_id, yaml) VALUES ('p_bf', 'u_bf', 'y')")
            )
            conn.execute(
                text(
                    "INSERT INTO conversations (id, owner_id, persona_id) "
                    "VALUES ('c_pre_v9', 'u_bf', 'p_bf')"
                )
            )
    finally:
        engine.dispose()

    # Now apply 020: its explicit UPDATE backfill must pin the orphan row to 'chat'.
    command.upgrade(cfg, "head")
    engine = create_engine(clean_db)
    try:
        with engine.begin() as conn:
            origin = conn.execute(
                text("SELECT origin FROM conversations WHERE id = 'c_pre_v9'")
            ).scalar_one()
        assert origin == "chat"
    finally:
        engine.dispose()

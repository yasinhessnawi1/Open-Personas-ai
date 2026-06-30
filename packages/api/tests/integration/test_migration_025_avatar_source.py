"""Migration 025 (personas.avatar_source) round-trip test (Spec R3, R3-D-2 / R3-D-5).

Proves the synthetic-media **provenance** column for the avatar surface (EU AI
Act Art. 50). At ``head`` the column is present and **nullable** (a string
``'generated'`` / ``'uploaded'`` / ``NULL`` — no SQL ENUM/CHECK, so the value
vocabulary is the app layer's, R3-D-2). The load-bearing operational property is
the **NULL = unknown backfill** (R3-D-5): a persona that existed *before* this
migration reads ``NULL`` afterwards — pre-existing avatars are not reliably
distinguishable post-hoc, so they read unknown rather than being mislabelled.
``downgrade`` removes the column.

Mirrors the migration-020 programmatic Alembic pattern (cwd-independent). Each
test resets the schema at start AND end so the shared integration DB is left
clean for other migration tests (no leftover ``alembic_version``).

Split-home note: ``001_initial`` is left UNTOUCHED; it builds the schema via
``metadata.create_all`` from the canonical models, which now declare
``avatar_source`` — so on a fresh DB the column already exists after ``001`` and
``025``'s guarded ``ADD COLUMN IF NOT EXISTS`` is an idempotent no-op. ``025`` is
the migration of record.
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


def _persona_columns(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return {c["name"] for c in inspect(engine).get_columns("personas")}
    finally:
        engine.dispose()


@pytest.fixture
def clean_db(database_url: str) -> Iterator[str]:
    """Reset the schema before and after so migration tests don't contaminate
    each other on the shared integration DB (no leftover alembic_version)."""
    _reset_schema(database_url)
    yield database_url
    _reset_schema(database_url)


def test_025_adds_and_removes_avatar_source_column(clean_db: str) -> None:
    cfg = _alembic_config(clean_db)

    # head: avatar_source present, nullable.
    command.upgrade(cfg, "head")
    assert "avatar_source" in _persona_columns(clean_db)
    engine = create_engine(clean_db)
    try:
        col = next(
            c for c in inspect(engine).get_columns("personas") if c["name"] == "avatar_source"
        )
        assert col["nullable"] is True
    finally:
        engine.dispose()

    # downgrade 025 -> its predecessor 024_credits_balance_floor: column dropped.
    command.downgrade(cfg, "024_credits_balance_floor")
    assert "avatar_source" not in _persona_columns(clean_db)


def test_avatar_source_accepts_generated_uploaded_and_null(clean_db: str) -> None:
    """The column stores ``'generated'`` / ``'uploaded'`` / ``NULL`` (no DB CHECK —
    the vocabulary is enforced at the app layer, R3-D-2). A persona written without
    a provenance value reads ``NULL`` = unknown."""
    cfg = _alembic_config(clean_db)
    command.upgrade(cfg, "head")

    engine = create_engine(clean_db)
    try:
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, email) VALUES ('u_025', 'u025@x.test')"))
            # no avatar_source given -> NULL (unknown)
            conn.execute(
                text("INSERT INTO personas (id, owner_id, yaml) VALUES ('p_null', 'u_025', 'y')")
            )
            conn.execute(
                text(
                    "INSERT INTO personas (id, owner_id, yaml, avatar_source) "
                    "VALUES ('p_gen', 'u_025', 'y', 'generated')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO personas (id, owner_id, yaml, avatar_source) "
                    "VALUES ('p_up', 'u_025', 'y', 'uploaded')"
                )
            )
        with engine.begin() as conn:
            null_src = conn.execute(
                text("SELECT avatar_source FROM personas WHERE id = 'p_null'")
            ).scalar_one()
            gen_src = conn.execute(
                text("SELECT avatar_source FROM personas WHERE id = 'p_gen'")
            ).scalar_one()
            up_src = conn.execute(
                text("SELECT avatar_source FROM personas WHERE id = 'p_up'")
            ).scalar_one()
        assert null_src is None
        assert gen_src == "generated"
        assert up_src == "uploaded"
    finally:
        engine.dispose()


def test_existing_rows_backfill_to_null_unknown(clean_db: str) -> None:
    """The R3-D-5 load-bearing property: a persona that exists BEFORE the
    ``avatar_source`` column reads ``NULL`` = unknown afterwards (no audit-backfill).

    This is the genuine DEPLOYED-DB path — a real Postgres that has the ``personas``
    table but NOT yet the ``avatar_source`` column. The split-home harness can't
    reach that state by stopping at an earlier revision (``001_initial`` builds the
    schema via ``metadata.create_all`` from the *current* canonical models, which
    already declare ``avatar_source``), so we reproduce it faithfully: upgrade to
    025's predecessor (024), DROP the column, rewind ``alembic_version`` to 024,
    insert a pre-existing row, and run 025 — asserting NO backfill UPDATE touches
    the orphan row (it stays NULL).
    """
    cfg = _alembic_config(clean_db)
    command.upgrade(cfg, "024_credits_balance_floor")

    engine = create_engine(clean_db)
    try:
        with engine.begin() as conn:
            # Simulate the real pre-R3 deployed schema: no avatar_source column.
            conn.execute(text("ALTER TABLE personas DROP COLUMN IF EXISTS avatar_source"))
            conn.execute(
                text("UPDATE alembic_version SET version_num = '024_credits_balance_floor'")
            )
        assert "avatar_source" not in _persona_columns(clean_db)
        with engine.begin() as conn:
            conn.execute(text("INSERT INTO users (id, email) VALUES ('u_bf', 'ubf@x.test')"))
            conn.execute(
                text(
                    "INSERT INTO personas (id, owner_id, yaml, avatar_url) "
                    "VALUES ('p_pre_r3', 'u_bf', 'y', 'uploads/legacy.png')"
                )
            )
    finally:
        engine.dispose()

    # Now apply 025: the orphan row must read NULL (no audit-backfill, R3-D-5).
    command.upgrade(cfg, "head")
    engine = create_engine(clean_db)
    try:
        with engine.begin() as conn:
            src = conn.execute(
                text("SELECT avatar_source FROM personas WHERE id = 'p_pre_r3'")
            ).scalar_one()
        assert src is None
    finally:
        engine.dispose()

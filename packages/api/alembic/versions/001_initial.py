"""Initial schema: all tables, indexes, pgvector extension, and RLS.

Spec 07, T04 (tables + indexes) and T06 (RLS policies). One atomic upgrade so a
freshly-migrated database is immediately tenant-safe (RLS lives here, not a
later revision — D-07-6).

Tables/indexes are created from the canonical ``persona_api.db.models``
``MetaData`` (the same object T03 verified builds correctly, including the
pgvector ``vector(384)`` column, the HNSW ``vector_cosine_ops`` index, and the
partial current-heads index). RLS enable/force + per-table policies are explicit
SQL via ``op.execute`` (D-07-5) — beyond Alembic autogenerate.

Revision ID: 001_initial
Revises:
"""

from __future__ import annotations

from alembic import op
from persona_api.db.models import metadata as _schema
from persona_api.db.rls import downgrade_rls_sql, upgrade_rls_sql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # Tables + all indexes (HNSW, partial current-heads, FK indexes) from the
    # canonical Core schema. Deterministic and drift-free vs the transport.
    _schema.create_all(bind)
    # Row-level security: enable + force + per-table policies (T06, D-07-5).
    for statement in upgrade_rls_sql():
        op.execute(statement)


def downgrade() -> None:
    bind = op.get_bind()
    for statement in downgrade_rls_sql():
        op.execute(statement)
    _schema.drop_all(bind)
    op.execute("DROP EXTENSION IF EXISTS vector")

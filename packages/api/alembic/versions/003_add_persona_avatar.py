"""Add the nullable ``personas.avatar_url`` column (pre-spec-09 patch).

A presentation field for the persona list / chat header — nullable (the
frontend uploads one or auto-generates from initials). Not part of the persona
YAML schema; an API-row presentation field.

Same idempotent pattern as ``002``: ``001_initial`` builds the schema via
``metadata.create_all`` from the *current* canonical models (which now declare
``avatar_url``), so on a fresh DB the column already exists when ``003`` runs and
``ADD COLUMN IF NOT EXISTS`` is a harmless no-op; on a DB that ran ``001`` before
this column was declared, ``003`` actually adds it. ``003`` is the migration of
record. Manual (``alembic upgrade head``), never auto-on-startup (spec 07 §7).

Revision ID: 003_add_persona_avatar
Revises: 002_add_message_channel
"""

from __future__ import annotations

from alembic import op

revision = "003_add_persona_avatar"
down_revision = "002_add_message_channel"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE personas ADD COLUMN IF NOT EXISTS avatar_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE personas DROP COLUMN IF EXISTS avatar_url")

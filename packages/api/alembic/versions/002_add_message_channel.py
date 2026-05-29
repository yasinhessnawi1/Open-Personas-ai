"""Add the nullable ``messages.channel`` JSONB column (spec 08, D-08-3).

The FIRST incremental migration (spec 07 shipped ``001_initial``) — the template
for every future schema change. It adds a single nullable JSONB column that
carries connector context (platform, platform_user_id, platform_chat_id,
metadata) as an opaque passthrough. The web UI sends nothing here (NULL); the
API stores whatever a connector passes and never interprets it. Nullable so it
does not disturb existing rows or the web-UI path.

Migrations are manual (``alembic upgrade head`` at deploy), never auto-on-startup
(spec 07 §7). The source-of-truth column is also declared on the canonical
``persona_api.db.models.messages`` table so the schema and the migration agree
(the split-home discipline).

Idempotent by design. ``001_initial`` (spec 07, left UNTOUCHED) builds the schema
via ``metadata.create_all`` from the *current* canonical models — which now
declare ``channel`` — so on a freshly-migrated DB the column already exists when
``002`` runs, and ``ADD COLUMN IF NOT EXISTS`` is a harmless no-op. On a DB that
ran ``001`` *before* this column was declared (a real deployed instance), ``002``
actually adds it. Either way the migration of record for ``messages.channel`` is
``002``; the ``IF [NOT] EXISTS`` guard is what makes it correct in both cases
without modifying spec-07's shipped ``001`` (see research §"implementation
findings"). The downgrade drops the column regardless.

Revision ID: 002_add_message_channel
Revises: 001_initial
"""

from __future__ import annotations

from alembic import op

revision = "002_add_message_channel"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS channel JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS channel")

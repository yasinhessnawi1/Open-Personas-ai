"""Add the nullable ``messages.tier_used`` column (Spec 35, D-35-2).

The routing tier (``small`` / ``mid`` / ``frontier``) the router chose for an
assistant turn, persisted so the per-message tier chip survives a page reload —
the live chat ``done`` event only carries the just-streamed turn, so a reloaded
conversation would otherwise show no chip. Written onto assistant rows only;
user / system / tool rows persist NULL.

Nullable by design: every message written before this migration carries NULL, so
the chip degrades to "no chip" on historical turns (never a wrong tier). The
source-of-truth column is also declared on the canonical
``persona_api.db.models.messages`` table so the schema and the migration agree
(the split-home discipline, per migration 002's template).

Idempotent: ``001_initial`` builds the schema via ``metadata.create_all`` from the
current canonical models (which now declare ``tier_used``), so on a freshly-built
DB the column already exists and ``ADD COLUMN IF NOT EXISTS`` is a harmless no-op;
on a previously-deployed DB it actually adds the column. The downgrade drops it.

Revision ID: 010_add_message_tier
Revises: 009_user_mcp_servers
"""

from __future__ import annotations

from alembic import op

revision = "010_add_message_tier"
down_revision = "009_user_mcp_servers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS tier_used TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE messages DROP COLUMN IF EXISTS tier_used")

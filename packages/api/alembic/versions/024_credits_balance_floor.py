"""Add ``credits.balance >= 0`` CHECK — the money-path durable floor (Spec R2, F-04 / R2-D-3).

The audit's F-04: the credits decrement had no balance floor, so concurrent
turns could double-spend the balance negative. R2 fixes the app path with a
conditional atomic decrement (``UPDATE … WHERE balance >= :amount RETURNING`` in
``persona.credits.service.deduct``); THIS migration adds the belt-and-braces
DB-level guard so a negative balance is unreachable regardless of any future
write path.

Two steps, in order:

1. **Repair** — any row already driven negative by the pre-fix code is clamped to
   ``0`` (``UPDATE credits SET balance = 0 WHERE balance < 0``), logged via the
   row count. Without this the constraint would fail to apply on a deployed DB.
2. **Constrain** — add ``CHECK (balance >= 0)`` named ``credits_balance_nonneg_check``.

Idempotent + split-home (cf. migrations 010 / 013 / 018 / 020 / 023): the same
constraint is declared on the canonical ``persona_api.db.models.credits`` table,
so on a fresh DB ``001_initial``'s ``metadata.create_all`` already built it and
the guarded ``DO`` block below is a harmless no-op; on a previously-deployed DB
it actually adds it. Both agree. ``ADD CONSTRAINT`` has no ``IF NOT EXISTS`` in
PostgreSQL, so a catalog guard (``pg_constraint`` lookup) provides idempotency.

Revision ID: 024_credits_balance_floor
Revises: 023_user_mcp_catalog_source
"""

from __future__ import annotations

from alembic import op

# PLACEHOLDER down_revision (R-19-1 chain numbering): chained off main's head at authoring
# time, ``023_user_mcp_catalog_source`` (N4) — the verified single head when R2 branched.
# Other in-flight specs (C-track / R-track) may land migrations before R2 merges, so this
# number + ``down_revision`` are RECOMPUTED at merge-back to preserve the single-head chain —
# do NOT rely on ``024`` / ``023`` surviving verbatim.
revision = "024_credits_balance_floor"
down_revision = "023_user_mcp_catalog_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Repair any pre-fix negative balances so the constraint can apply.
    op.execute("UPDATE credits SET balance = 0 WHERE balance < 0")
    # 2. Add the CHECK idempotently (no ADD CONSTRAINT IF NOT EXISTS in PG → catalog guard).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'credits_balance_nonneg_check'
            ) THEN
                ALTER TABLE credits
                    ADD CONSTRAINT credits_balance_nonneg_check CHECK (balance >= 0);
            END IF;
        END
        $$
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE credits DROP CONSTRAINT IF EXISTS credits_balance_nonneg_check")

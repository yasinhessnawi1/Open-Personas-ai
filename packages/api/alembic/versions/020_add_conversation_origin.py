"""Add the ``conversations.origin`` birth-marker (Spec V9, V9-D-3).

V9 gives voice calls a first-class browsable home. The linchpin is a single
shared **origin** attribute on the conversation — ``'chat'`` (text-born) or
``'call'`` (voice-born) — set ONCE at creation and **immutable**. It is the
ONLY seam between chat and voice: the chat list excludes ``'call'`` (killing the
empty-"Untitled conversation" pollution), the Calls surface reads the
call-record; neither domain inspects the other's internals (V9-D-3).

This migration adds ``conversations.origin TEXT NOT NULL DEFAULT 'chat'`` + a
CHECK constraining it to ``{chat, call}``. The sequence is the safe,
**explicitly-backfilled** add (the T1 carry-item — pin the backfill, don't lean
on ADD-COLUMN-NOT-NULL-DEFAULT's implicit one):

  1. ADD COLUMN IF NOT EXISTS origin TEXT          (nullable first — never locks)
  2. UPDATE ... SET origin='chat' WHERE origin IS NULL   (explicit backfill: every
     pre-V9 conversation is chat-born)
  3. ALTER COLUMN origin SET DEFAULT 'chat'
  4. ALTER COLUMN origin SET NOT NULL
  5. guarded CHECK (origin IN ('chat','call'))

Every step is idempotent (``IF NOT EXISTS`` / ``WHERE origin IS NULL`` /
``pg_constraint`` guard), so re-running is a no-op. Inherits the existing
``conversations`` RLS policy — no new policy DDL.

Split-home note: ``001_initial`` is left UNTOUCHED; it builds the schema via
``metadata.create_all`` from the canonical models, which now declare ``origin``
+ the CHECK — so on a fresh DB the column already exists after ``001`` and the
guarded DDL below is a harmless no-op; on a previously-deployed DB it actually
adds + backfills it. The source-of-truth column/CHECK are declared on the
canonical ``persona_api.db.models.conversations`` table so schema and migration
agree (the split-home discipline, per migrations 010 / 013 / 018).

Revision ID: 020_add_conversation_origin
Revises: 019_task_model
"""

from __future__ import annotations

from alembic import op

# Linearized at merge-back (R-19-1 chain numbering): V9's origin-marker migration
# lands as 020, chained off A2's head 019_task_model (single-head discipline; one
# worktree lands a migration at a time). V9 + A2 were the two migration-bearing
# in-flight specs; A2 merged first (019_task_model), so V9's chain re-points above
# it at merge-back. conversations.origin is V9's only touch to the conversations table.
revision = "020_add_conversation_origin"
down_revision = "019_task_model"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) add nullable (never takes a lengthy lock / table rewrite).
    op.execute("ALTER TABLE conversations ADD COLUMN IF NOT EXISTS origin TEXT")
    # 2) EXPLICIT backfill — every pre-V9 conversation is chat-born (T1 carry-item).
    op.execute("UPDATE conversations SET origin = 'chat' WHERE origin IS NULL")
    # 3) + 4) pin the default and the NOT NULL now that no row is NULL.
    op.execute("ALTER TABLE conversations ALTER COLUMN origin SET DEFAULT 'chat'")
    op.execute("ALTER TABLE conversations ALTER COLUMN origin SET NOT NULL")
    # 5) guarded CHECK (ADD CONSTRAINT has no IF NOT EXISTS; create_all may already
    # have added it on a fresh DB).
    op.execute(
        """
        DO $$ BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname = 'conversations_origin_check'
          ) THEN
            ALTER TABLE conversations ADD CONSTRAINT conversations_origin_check
              CHECK (origin IN ('chat', 'call'));
          END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_origin_check")
    op.execute("ALTER TABLE conversations DROP COLUMN IF EXISTS origin")

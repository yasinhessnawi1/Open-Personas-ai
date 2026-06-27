"""Add the ``calls`` call-record table (Spec V9, V9-D-5).

A voice call's lifecycle envelope — ``call_id``, ``conversation_id``,
``persona_id``, ``owner_id``, ``started_at``, ``ended_at``, ``duration_s``,
``end_reason`` — persisted NOWHERE server-side before V9 (it lived only in the
in-memory ``SessionStateMachine`` + client storage). This is the durable home,
and the **Calls-surface membership key** (a conversation appears in Calls iff it
has a ``calls`` row — V9-D-3 — NOT via ``origin``).

The voice runtime (API-free: ``voice → runtime → core``) WRITES this via a
core-owned ``_calls`` Table view (``persona.calls``) on its session RLS engine —
the ``memory_chunks`` P2 precedent; a contract test guards the view↔DDL drift.

RLS: owner-scoped, like ``conversations``. ENABLE + FORCE + a ``user_isolation``
policy ``USING/WITH CHECK (owner_id = current_setting('app.current_user_id'))``,
created ENTIRELY in this migration (the 009/011/012/015 split-home template;
deliberately NOT in ``db/rls._POLICIES``). ``ON DELETE CASCADE`` on both FKs →
deleting a conversation (or user) cleans its call-records for free (v1 retention).

Idempotent: ``Table.create(checkfirst=True)`` (``001_initial`` already builds it
on a fresh DB from the canonical models, so this is a no-op there) + guarded
``DROP POLICY IF EXISTS`` before ``CREATE POLICY``.

Revision ID: 021_add_calls_table
Revises: 020_add_conversation_origin
"""

from __future__ import annotations

from alembic import op
from persona_api.db.models import calls

# Linearized at merge-back (R-19-1): V9 carries TWO migrations — 020 (origin) +
# 021 (calls) — chained off 020_add_conversation_origin. V9 + A2 were the two
# migration-bearing in-flight specs; A2 merged first (019_task_model), so the full
# V9 chain re-points above it at merge-back.
revision = "021_add_calls_table"
down_revision = "020_add_conversation_origin"
branch_labels = None
depends_on = None

# owner-scoped RLS predicate (mirrors conversations / synthesis_markers).
_CUR = "current_setting('app.current_user_id', true)"
_RLS_PREDICATE = f"owner_id = {_CUR}"


def upgrade() -> None:
    bind = op.get_bind()
    calls.create(bind, checkfirst=True)
    op.execute("ALTER TABLE calls ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE calls FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS user_isolation ON calls")
    op.execute(
        f"CREATE POLICY user_isolation ON calls USING ({_RLS_PREDICATE}) "
        f"WITH CHECK ({_RLS_PREDICATE})"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS user_isolation ON calls")
    op.execute("ALTER TABLE calls NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE calls DISABLE ROW LEVEL SECURITY")
    op.execute("DROP TABLE IF EXISTS calls")

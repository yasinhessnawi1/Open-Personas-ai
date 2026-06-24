"""Durable schedules: the ``schedules`` table + RLS (Spec A1, T3).

Adds A1's clock — a durable, RLS-scoped ``schedules`` table holding a recurring
RRULE-class rule OR a one-time future instant, with the user's captured IANA
timezone on the row. The single-leader tick (in the A0 worker) claims due rows
and materialises each fire into an A0 ``jobs`` row keyed by ``sched:{id}:{t}``,
riding A0's effectively-once guarantee. Owner-scoped + RLS like every tenant
table — the worker connects as the ``persona_app`` non-superuser role for
creation, so a missed scope fails CLOSED (zero rows), never leaks.

Unlike the hot ``jobs`` queue (migration 012), ``schedules`` is a LOW-VOLUME
entity table (one row per schedule, updated once per fire), so it carries NO
queue-hygiene reloptions (``fillfactor``/aggressive autovacuum) — default
autovacuum is correct; adding them would be cargo-culting.

Follows the 012 template: the table is created from the canonical ``MetaData``
with ``checkfirst=True`` (idempotent — a fresh-install ``001`` ``create_all``
already made it, since it is now in ``persona_api.db.models``); RLS via explicit
SQL with ``DROP POLICY IF EXISTS`` before ``CREATE`` (idempotent re-run /
fresh-DB overlap). Manual (``alembic upgrade head``), never auto-on-startup.

The RLS policy is deliberately NOT added to ``persona_api.db.rls._POLICIES``
(that drives ``001``'s downgrade, which must not ALTER a table created later);
this migration owns its full lifecycle, exactly as 009/012 do.

**Migration-slot coordination (D-A1-X-migration-placeholder):** renumbered at
merge-back from the provisional ``013_schedules`` / ``012_jobs_queue`` to the
final ``014_schedules`` chaining off main's head ``013_add_message_originated``,
keeping the canonical chain linear:
``... → 012_jobs_queue → 013_add_message_originated → 014_schedules``.

Revision ID: 014_schedules
Revises: 013_add_message_originated
"""

from __future__ import annotations

from alembic import op
from persona_api.db.models import schedules

revision = "014_schedules"
down_revision = "013_add_message_originated"
branch_labels = None
depends_on = None

_CUR = "current_setting('app.current_user_id', true)"

# (table, USING/WITH CHECK predicate) — direct owner_id scope, mirrors
# persona_api.db.rls._POLICIES + migration 012. current_setting(..., true) fails
# CLOSED (an unset GUC yields NULL, which matches no row).
_RLS_PREDICATE = f"owner_id = {_CUR}"


def upgrade() -> None:
    bind = op.get_bind()
    schedules.create(bind, checkfirst=True)
    op.execute("ALTER TABLE schedules ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schedules FORCE ROW LEVEL SECURITY")
    # DROP IF EXISTS keeps this idempotent + avoids clashing with a policy a
    # fresh-install 001 might already have created (the table is in metadata).
    op.execute("DROP POLICY IF EXISTS user_isolation ON schedules")
    op.execute(
        "CREATE POLICY user_isolation ON schedules "
        f"USING ({_RLS_PREDICATE}) WITH CHECK ({_RLS_PREDICATE})"
    )
    # D-A1-X-rls-chokepoint seam (mirrors 012): the tick's dispatch engine reads +
    # updates schedules cross-tenant (claim due rows, advance bookkeeping). If the
    # least-privilege ``job_dispatcher`` role exists (provisioned out-of-band —
    # D-07-5, roles are NOT created in migrations), grant it SELECT + UPDATE only.
    # NOT INSERT: schedule creation goes through the owner-scoped RLS engine
    # (mirrors A0's enqueue-vs-dispatch split). Conditional + idempotent.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'job_dispatcher') THEN
                GRANT SELECT, UPDATE ON schedules TO job_dispatcher;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    op.execute("DROP POLICY IF EXISTS user_isolation ON schedules")
    op.execute("ALTER TABLE schedules NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE schedules DISABLE ROW LEVEL SECURITY")
    schedules.drop(bind, checkfirst=True)

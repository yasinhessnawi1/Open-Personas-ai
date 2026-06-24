"""Migration + RLS + constraint + claim-index tests for ``schedules`` (Spec A1, T3).

Runs against a real Postgres built by ``alembic upgrade head`` (so migration
``014_schedules`` and its RLS policy are present). Four concerns:

1. **Table + columns + valid inserts** — a recurring row and a one-time row each
   insert cleanly with the server-side defaults.
2. **Constraints** — the recurrence/one-time XOR rejects both-set AND neither-set;
   the missed-fire-policy / grace / fire-count checks reject bad values.
3. **RLS tenant isolation** (adversarial, the standing gate) — seed two tenants as
   superuser, then under each user's RLS context as the NON-SUPERUSER
   ``persona_app`` role assert zero cross-tenant rows + WITH CHECK blocks a
   cross-tenant insert + fail-closed when the GUC is unset.
4. **Due-index proof** — EXPLAIN shows the partial ``idx_schedules_due`` index
   serves the tick's due-claim predicate.

The non-superuser role is mandatory: superusers bypass RLS even under FORCE.
``APP_DATABASE_URL`` provides the role DSN; the RLS tests skip if it is unset.
"""

# ruff: noqa: ARG001 — ``migrated_engine`` is a dependency-ordering fixture param.
from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from persona_api.db.engine import rls_connection
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError, ProgrammingError

pytestmark = pytest.mark.integration

_RRULE = "FREQ=DAILY;BYHOUR=7;BYMINUTE=0"


@pytest.fixture
def app_engine(migrated_engine: Engine) -> Iterator[Engine]:
    """A non-superuser (``persona_app``) engine for the RLS-under-test connection.

    Depends on ``migrated_engine`` so the migrated schema + grants exist first.
    Skips if ``APP_DATABASE_URL`` is unset (role provisioned out-of-band). Disposed
    at teardown so no pooled connection lingers into the next test's DROP SCHEMA.
    """
    app_url = os.environ.get("APP_DATABASE_URL")
    if not app_url:
        pytest.skip("APP_DATABASE_URL (non-superuser role) not set; skipping RLS test")
    engine = create_engine(app_url.replace("+asyncpg", "+psycopg"))
    yield engine
    engine.dispose()


def _seed_user(engine: Engine, user_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email) VALUES (:u, :e)"),
            {"u": user_id, "e": f"{user_id}@example.com"},
        )


# --- table + valid inserts --------------------------------------------------


def test_recurring_schedule_inserts_with_defaults(migrated_engine: Engine) -> None:
    _seed_user(migrated_engine, "user_a")
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, recurrence, target_job_type) "
                "VALUES ('s1','user_a','Europe/Oslo',:r,'briefing')"
            ),
            {"r": _RRULE},
        )
        row = conn.execute(
            text(
                "SELECT enabled, paused, missed_fire_policy, fire_count, "
                "payload_template, created_at, updated_at, one_time_at "
                "FROM schedules WHERE id = 's1'"
            )
        ).one()
    assert row.enabled is True
    assert row.paused is False
    assert row.missed_fire_policy == "fire-late-once"
    assert row.fire_count == 0
    assert row.payload_template == {}
    assert row.one_time_at is None
    assert row.created_at is not None
    assert row.updated_at is not None


def test_one_time_schedule_inserts(migrated_engine: Engine) -> None:
    _seed_user(migrated_engine, "user_a")
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, one_time_at, target_job_type) "
                "VALUES ('s1','user_a','Europe/Oslo', now() + interval '1 day','reminder')"
            )
        )
        row = conn.execute(
            text("SELECT recurrence, one_time_at FROM schedules WHERE id = 's1'")
        ).one()
    assert row.recurrence is None
    assert row.one_time_at is not None


# --- constraints ------------------------------------------------------------


def test_xor_rejects_both_recurrence_and_one_time(migrated_engine: Engine) -> None:
    _seed_user(migrated_engine, "user_a")
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, recurrence, one_time_at, "
                "target_job_type) VALUES "
                "('s1','user_a','Europe/Oslo',:r, now() + interval '1 day','briefing')"
            ),
            {"r": _RRULE},
        )


def test_xor_rejects_neither_recurrence_nor_one_time(migrated_engine: Engine) -> None:
    _seed_user(migrated_engine, "user_a")
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, target_job_type) "
                "VALUES ('s1','user_a','Europe/Oslo','briefing')"
            )
        )


def test_missed_fire_policy_check_rejects_unknown(migrated_engine: Engine) -> None:
    _seed_user(migrated_engine, "user_a")
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, recurrence, target_job_type, "
                "missed_fire_policy) VALUES ('s1','user_a','Europe/Oslo',:r,'b','bogus')"
            ),
            {"r": _RRULE},
        )


def test_negative_grace_seconds_rejected(migrated_engine: Engine) -> None:
    _seed_user(migrated_engine, "user_a")
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, recurrence, target_job_type, "
                "grace_seconds) VALUES ('s1','user_a','Europe/Oslo',:r,'b',-1)"
            ),
            {"r": _RRULE},
        )


def test_negative_fire_count_rejected(migrated_engine: Engine) -> None:
    _seed_user(migrated_engine, "user_a")
    with pytest.raises(IntegrityError), migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, recurrence, target_job_type, "
                "fire_count) VALUES ('s1','user_a','Europe/Oslo',:r,'b',-1)"
            ),
            {"r": _RRULE},
        )


# --- RLS tenant isolation (adversarial) -------------------------------------


def _seed_two_tenants(superuser_engine: Engine) -> None:
    with superuser_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO users (id, email) VALUES "
                "('user_a','a@example.com'),('user_b','b@example.com')"
            )
        )
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, recurrence, target_job_type) "
                "VALUES ('sa','user_a','Europe/Oslo',:r,'briefing'),"
                "('sb','user_b','America/New_York',:r,'briefing')"
            ),
            {"r": _RRULE},
        )


def test_schedules_isolated_per_tenant(migrated_engine: Engine, app_engine: Engine) -> None:
    _seed_two_tenants(migrated_engine)
    with rls_connection(app_engine, "user_a") as conn:
        owners = {r.owner_id for r in conn.execute(text("SELECT owner_id FROM schedules")).all()}
    assert owners == {"user_a"}, f"RLS leak on schedules: user_a saw {owners}"


def test_schedules_cross_tenant_write_blocked_by_with_check(
    migrated_engine: Engine, app_engine: Engine
) -> None:
    _seed_two_tenants(migrated_engine)
    with (
        rls_connection(app_engine, "user_a") as conn,
        pytest.raises(ProgrammingError),
    ):
        conn.execute(
            text(
                "INSERT INTO schedules (id, owner_id, timezone, recurrence, target_job_type) "
                "VALUES ('evil','user_b','Europe/Oslo',:r,'briefing')"
            ),
            {"r": _RRULE},
        )


def test_schedules_unset_user_sees_nothing_fail_closed(
    migrated_engine: Engine, app_engine: Engine
) -> None:
    _seed_two_tenants(migrated_engine)
    with app_engine.begin() as conn:
        rows = conn.execute(text("SELECT id FROM schedules")).all()
    assert rows == [], "schedules RLS must fail closed when app.current_user_id is unset"


# --- due-index proof --------------------------------------------------------


def test_due_query_uses_partial_due_index(migrated_engine: Engine) -> None:
    # Seed enough due rows that the planner would consider the index, then force
    # index preference and assert the tick's due-claim plans onto idx_schedules_due.
    _seed_user(migrated_engine, "user_a")
    with migrated_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO schedules "
                "(id, owner_id, timezone, recurrence, target_job_type, next_fire_at) "
                "SELECT 'sch_' || g, 'user_a', 'Europe/Oslo', :r, 'briefing', "
                "now() + (g || ' minutes')::interval "
                "FROM generate_series(1, 500) AS g"
            ),
            {"r": _RRULE},
        )
        conn.execute(text("ANALYZE schedules"))
        conn.execute(text("SET LOCAL enable_seqscan = off"))
        plan = "\n".join(
            row[0]
            for row in conn.execute(
                text(
                    "EXPLAIN SELECT id FROM schedules "
                    "WHERE enabled AND NOT paused AND next_fire_at IS NOT NULL "
                    "AND next_fire_at <= now() ORDER BY next_fire_at "
                    "FOR UPDATE SKIP LOCKED LIMIT 100"
                )
            ).all()
        )
    assert "idx_schedules_due" in plan, f"due query did not use the partial index; plan:\n{plan}"

"""Downtime-simulation tests for the missed-fire policy (Spec A1, T7) — criterion 5.

Real Postgres. Simulates "the worker was down across a fire time" by forcing a
schedule's ``next_fire_at`` into the past, then running one tick with a fixed
``now``. Proves:

* **fire-late-once within grace** catches up EXACTLY once, then jumps to the
  future (no burst), noted ``schedule.fire_late``;
* **fire-late-once beyond grace** skips + notes (``schedule.miss``), fires next on
  schedule — no catch-up;
* **skip-and-note** never catches up (skips + notes even within a grace window);
* **on-time** fires normally regardless of policy;
* **NO BURST in any config** — a long-missed schedule yields at most one
  job/note per tick and jumps to the future;
* **one-time completion** — a skipped or late one-time terminates (``next_fire_at
  = None``).
"""

# ruff: noqa: ARG001 — ``migrated_engine`` is a dependency-ordering fixture param.
from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from persona.schedules import MissedFirePolicy, RecurrenceFreq, RecurrenceRule, Schedule
from persona_api.schedules import SchedulerLeader, SchedulerTick, ScheduleStore
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

_NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
_GRACE = 10_800.0  # 3h
_ONE_TIME_GRACE = 3_600.0  # 1h
_TOL = 120.0  # 2min
_LOCK_KEY = 0x5C4ED7


@pytest.fixture
def app_engine(migrated_engine: Engine) -> Iterator[Engine]:
    app_url = os.environ.get("APP_DATABASE_URL")
    if not app_url:
        pytest.skip("APP_DATABASE_URL (non-superuser role) not set; skipping RLS test")
    engine = create_engine(app_url.replace("+asyncpg", "+psycopg"))
    yield engine
    engine.dispose()


@pytest.fixture
def store(app_engine: Engine) -> ScheduleStore:
    return ScheduleStore(app_engine)


@pytest.fixture
def dispatch_engine(migrated_engine: Engine, database_url: str) -> Iterator[Engine]:
    """A dedicated, per-test superuser engine for the tick + leader (off the
    session pool — see ``test_scheduler_tick.py``'s fixture for the rationale:
    the leader's long-lived advisory-lock connection must not ride the shared
    session pool the conftest's stale-connection guard manages)."""
    engine = create_engine(database_url.replace("+asyncpg", "+psycopg"))
    yield engine
    engine.dispose()


@pytest.fixture
def leader(dispatch_engine: Engine) -> Iterator[SchedulerLeader]:
    lead = SchedulerLeader(dispatch_engine, lock_key=_LOCK_KEY)
    yield lead
    lead.resign()


@pytest.fixture
def tick(dispatch_engine: Engine, app_engine: Engine, leader: SchedulerLeader) -> SchedulerTick:
    return SchedulerTick(
        dispatch_engine=dispatch_engine,
        rls_engine=app_engine,
        leader=leader,
        default_grace_seconds=_GRACE,
        one_time_grace_seconds=_ONE_TIME_GRACE,
        on_time_tolerance_seconds=_TOL,
    )


def _seed_user(engine: Engine, uid: str = "user_a") -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email) VALUES (:u, :e)"),
            {"u": uid, "e": f"{uid}@example.com"},
        )


def _make_due(
    superuser_engine: Engine,
    store: ScheduleStore,
    *,
    due_at: datetime,
    policy: MissedFirePolicy = MissedFirePolicy.FIRE_LATE_ONCE,
    one_time: bool = False,
    schedule_id: str = "s1",
    owner: str = "user_a",
) -> None:
    created = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    store.create(
        Schedule(
            id=schedule_id,
            owner_id=owner,
            timezone="Europe/Oslo",
            recurrence=None
            if one_time
            else RecurrenceRule(freq=RecurrenceFreq.DAILY, byhour=(7,), byminute=(0,)),
            one_time_at=due_at if one_time else None,
            target_job_type="briefing",
            missed_fire_policy=policy,
            created_at=created,
            updated_at=created,
        ),
        now=created,
    )
    with superuser_engine.begin() as conn:
        conn.execute(
            text("UPDATE schedules SET next_fire_at = :d WHERE id = :i"),
            {"d": due_at, "i": schedule_id},
        )


def _audit_actions(engine: Engine, target: str = "s1") -> list[str]:
    with engine.begin() as conn:
        return [
            r.action
            for r in conn.execute(
                text("SELECT action FROM audit_log WHERE target = :t"), {"t": target}
            ).all()
        ]


def _job_count(engine: Engine, owner: str = "user_a") -> int:
    with engine.begin() as conn:
        return conn.execute(
            text("SELECT count(*) FROM jobs WHERE owner_id = :o"), {"o": owner}
        ).scalar_one()


# --- fire-late-once ---------------------------------------------------------


def test_fire_late_once_within_grace_catches_up_exactly_once(
    migrated_engine: Engine, store: ScheduleStore, tick: SchedulerTick
) -> None:
    _seed_user(migrated_engine)
    _make_due(migrated_engine, store, due_at=_NOW - timedelta(minutes=30))  # 30min late < 3h
    assert tick.run_once(now=_NOW) == 1  # caught up
    assert _job_count(migrated_engine) == 1
    fired = store.get("user_a", "s1")
    assert fired.fire_count == 1
    assert fired.next_fire_at is not None
    assert fired.next_fire_at > _NOW  # jumped to the future — rhythm resumes
    assert "schedule.fire_late" in _audit_actions(migrated_engine)  # durable late note
    # Second tick: already caught up + jumped forward → nothing due (no burst).
    assert tick.run_once(now=_NOW) == 0
    assert _job_count(migrated_engine) == 1


def test_fire_late_once_beyond_grace_skips_and_notes(
    migrated_engine: Engine, store: ScheduleStore, tick: SchedulerTick
) -> None:
    _seed_user(migrated_engine)
    _make_due(migrated_engine, store, due_at=_NOW - timedelta(hours=4))  # 4h late > 3h grace
    assert tick.run_once(now=_NOW) == 0  # not fired (counts as skipped, not fired)
    assert _job_count(migrated_engine) == 0  # no catch-up job
    skipped = store.get("user_a", "s1")
    assert skipped.fire_count == 0  # no fire happened
    assert skipped.next_fire_at is not None
    assert skipped.next_fire_at > _NOW  # advanced past the backlog
    assert "schedule.miss" in _audit_actions(migrated_engine)  # durable miss note


# --- skip-and-note ----------------------------------------------------------


def test_skip_and_note_never_catches_up(
    migrated_engine: Engine, store: ScheduleStore, tick: SchedulerTick
) -> None:
    _seed_user(migrated_engine)
    # 30min late — would be within a fire-late grace, but skip-and-note never catches up.
    _make_due(
        migrated_engine,
        store,
        due_at=_NOW - timedelta(minutes=30),
        policy=MissedFirePolicy.SKIP_AND_NOTE,
    )
    assert tick.run_once(now=_NOW) == 0
    assert _job_count(migrated_engine) == 0
    assert store.get("user_a", "s1").fire_count == 0
    assert "schedule.miss" in _audit_actions(migrated_engine)
    assert store.get("user_a", "s1").next_fire_at > _NOW  # next regular fire proceeds


# --- on-time (both policies) ------------------------------------------------


@pytest.mark.parametrize("policy", list(MissedFirePolicy))
def test_on_time_fire_fires_normally(
    migrated_engine: Engine, store: ScheduleStore, tick: SchedulerTick, policy: MissedFirePolicy
) -> None:
    _seed_user(migrated_engine)
    _make_due(migrated_engine, store, due_at=_NOW - timedelta(seconds=30), policy=policy)
    assert tick.run_once(now=_NOW) == 1  # within tolerance → normal fire
    assert _job_count(migrated_engine) == 1
    assert store.get("user_a", "s1").fire_count == 1
    actions = _audit_actions(migrated_engine)
    assert "schedule.fire" in actions  # an on-time fire, not a late note
    assert "schedule.fire_late" not in actions


# --- no burst in any config -------------------------------------------------


def test_long_downtime_never_bursts(
    migrated_engine: Engine, store: ScheduleStore, tick: SchedulerTick
) -> None:
    _seed_user(migrated_engine)
    # Worker down 10 days (10 missed daily occurrences), fire-late-once. 10 days >>
    # 3h grace → skip the stale backlog with a single note, jump to the future.
    _make_due(migrated_engine, store, due_at=_NOW - timedelta(days=10))
    assert tick.run_once(now=_NOW) == 0  # skipped (beyond grace), not 10 catch-ups
    assert _job_count(migrated_engine) == 0
    assert store.get("user_a", "s1").next_fire_at > _NOW
    # Repeated ticks never replay the backlog.
    assert tick.run_once(now=_NOW) == 0
    assert _job_count(migrated_engine) == 0
    assert _audit_actions(migrated_engine).count("schedule.miss") == 1  # one note, not ten


# --- one-time completion ----------------------------------------------------


def test_one_time_late_within_grace_fires_and_completes(
    migrated_engine: Engine, store: ScheduleStore, tick: SchedulerTick
) -> None:
    _seed_user(migrated_engine)
    _make_due(migrated_engine, store, due_at=_NOW - timedelta(minutes=30), one_time=True)
    assert tick.run_once(now=_NOW) == 1
    assert _job_count(migrated_engine) == 1
    done = store.get("user_a", "s1")
    assert done.fire_count == 1
    assert done.next_fire_at is None  # one-time COMPLETION (terminal)
    assert not done.is_active


def test_one_time_skipped_beyond_grace_terminates(
    migrated_engine: Engine, store: ScheduleStore, tick: SchedulerTick
) -> None:
    _seed_user(migrated_engine)
    _make_due(migrated_engine, store, due_at=_NOW - timedelta(hours=2), one_time=True)  # > 1h grace
    assert tick.run_once(now=_NOW) == 0  # skipped (beyond one-time grace)
    assert _job_count(migrated_engine) == 0
    done = store.get("user_a", "s1")
    assert done.fire_count == 0
    assert done.next_fire_at is None  # a skipped one-time still terminates (never fires)
    assert "schedule.miss" in _audit_actions(migrated_engine)

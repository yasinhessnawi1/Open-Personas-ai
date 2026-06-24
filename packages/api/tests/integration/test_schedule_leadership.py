"""Integration tests for scheduler-leader election (Spec A1, T5) — D-A1-5.

Real Postgres (advisory locks are server state — no mock is faithful). Proves:

* **Two contenders → one leader** — the session-scoped ``pg_try_advisory_lock`` on
  a dedicated connection admits exactly one holder; the other gets ``False``.
* **Handover on resign** — the leader releases, the follower acquires next attempt.
* **Handover on leader death** — the held session is hard-killed (crash sim);
  Postgres releases the lock and the follower acquires within a bounded retry.
* **Overlap window harmless (criterion 4 ↔ 6)** — two ticks briefly overlapping
  materialise the SAME ``schedule_id+fire_time`` key into A0's queue, and
  ``ON CONFLICT DO NOTHING`` yields exactly one job per (schedule, fire_time).
  The lock reduces redundant work; the idempotency key is the correctness floor.
"""

# ruff: noqa: ARG001 — ``migrated_engine`` is a dependency-ordering fixture param.
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from persona_api.jobs.queue import JobQueue
from persona_api.schedules import SchedulerLeader
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

pytestmark = pytest.mark.integration

# A distinct advisory-lock key per test keeps concurrent/repeated runs isolated.


@pytest.fixture
def dispatch_engine(migrated_engine: Engine, database_url: str) -> Iterator[Engine]:
    """A dedicated, per-test superuser engine the leaders run on.

    NOT the session-scoped ``migrated_engine``: a ``SchedulerLeader`` holds a
    long-lived AUTOCOMMIT advisory-lock connection, which on the shared session
    pool defeats the conftest's stale-connection dispose-guard (sporadic
    ``relation … does not exist``) and can bleed the lock across tests. A fresh
    engine disposed at teardown isolates it (the ``app_engine`` pattern). Depends
    on ``migrated_engine`` so the schema is migrated + truncated first.
    """
    engine = create_engine(database_url.replace("+asyncpg", "+psycopg"))
    yield engine
    engine.dispose()


def test_two_contenders_yield_one_leader(dispatch_engine: Engine) -> None:
    a = SchedulerLeader(dispatch_engine, lock_key=0x5C_4ED_010)
    b = SchedulerLeader(dispatch_engine, lock_key=0x5C_4ED_010)
    try:
        assert a.try_become_leader() is True
        assert b.try_become_leader() is False  # contention — exactly one leader
        assert a.is_leader
        assert not b.is_leader
        # Idempotent: the leader re-confirming does not re-lock or lose leadership.
        assert a.try_become_leader() is True
    finally:
        a.resign()
        b.resign()


def test_handover_after_graceful_resign(dispatch_engine: Engine) -> None:
    a = SchedulerLeader(dispatch_engine, lock_key=0x5C_4ED_020)
    b = SchedulerLeader(dispatch_engine, lock_key=0x5C_4ED_020)
    try:
        assert a.try_become_leader() is True
        assert b.try_become_leader() is False
        a.resign()  # leader steps down (drain/shutdown)
        assert b.try_become_leader() is True  # follower takes over on next attempt
        assert b.is_leader
    finally:
        a.resign()
        b.resign()


def test_handover_after_leader_death(dispatch_engine: Engine) -> None:
    a = SchedulerLeader(dispatch_engine, lock_key=0x5C_4ED_030)
    b = SchedulerLeader(dispatch_engine, lock_key=0x5C_4ED_030)
    try:
        assert a.try_become_leader() is True
        assert b.try_become_leader() is False
        # Simulate a crash: hard-kill the held DBAPI session (white-box). The TCP
        # session dies → Postgres releases the session-scoped lock, exactly as a
        # process kill would. No graceful unlock is sent.
        assert a._conn is not None  # noqa: SLF001 — crash sim needs the held conn
        a._conn.invalidate()  # noqa: SLF001
        # The follower acquires on its next attempt (bounded by the tick interval).
        assert b.try_become_leader() is True
        assert b.is_leader
    finally:
        a.resign()
        b.resign()


def test_overlap_window_harmless_via_idempotency_key(migrated_engine: Engine) -> None:
    # Two ticks (an old leader finishing + a new leader starting) materialise the
    # SAME due fire. The deterministic key makes the second enqueue a no-op.
    owner = "user_a"
    with migrated_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email) VALUES (:u, 'a@example.com')"),
            {"u": owner},
        )
    queue = JobQueue(migrated_engine)
    fire_time = datetime(2026, 3, 10, 11, 0, tzinfo=UTC)
    key = f"sched:sched-1:{fire_time.isoformat()}"  # the schedule_id+fire_time key

    first = queue.enqueue(
        type="briefing",
        owner_id=owner,
        payload={"schedule_id": "sched-1", "fire_time": fire_time.isoformat()},
        idempotency_key=key,
    )
    second = queue.enqueue(  # the overlapping tick's duplicate materialisation
        type="briefing",
        owner_id=owner,
        payload={"schedule_id": "sched-1", "fire_time": fire_time.isoformat()},
        idempotency_key=key,
    )
    assert first is not None  # first materialisation created the job
    assert second is None  # duplicate (same key) → ON CONFLICT DO NOTHING no-op

    with migrated_engine.begin() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM jobs WHERE idempotency_key = :k"), {"k": key}
        ).scalar()
    assert count == 1  # exactly one job per (schedule, fire_time)

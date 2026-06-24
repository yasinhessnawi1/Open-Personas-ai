"""Single-leader election for the scheduler tick (Spec A1, T5) — D-A1-5.

Exactly one worker process runs the scheduler tick at a time, elected by a
**session-scoped Postgres advisory lock** held on a **dedicated connection**:

    SELECT pg_try_advisory_lock(:key)   -- non-blocking; True ⟹ this worker leads

The holder is the leader and ticks; the rest get ``False`` and skip the tick
(they keep doing normal A0 job work). Boring and sufficient — no leader-election
framework (the spec's anti-goal).

**Session-scoped, deliberately (D-A1-5).** ``pg_try_advisory_lock`` holds until
explicit unlock OR the session ends — so it spans the leader's whole lifetime,
which is what leadership needs. This is the OPPOSITE primitive from A0's fairness,
which found the transaction-scoped ``pg_advisory_xact_lock`` mechanically wrong
for a duration-spanning need and uses a count-filtered claim with NO advisory lock
(D-A0-6). Different problems, different mechanisms.

**Dedicated connection, outside transaction pooling.** The lock lives on the
DBAPI *session*, so the leader checks out ONE connection and HOLDS it for the
duration of leadership — the pool can never hand that physical connection to
another client while it is held (the PgBouncer-transaction-mode hazard). The
connection runs in ``AUTOCOMMIT`` so it never sits idle-in-transaction pinning
the xmin horizon; the advisory lock is unaffected by autocommit because it is
session-scoped, not transaction-scoped.

**Handover + the overlap window (criterion 4 ↔ 6).** On leader death the TCP
session drops and Postgres releases the lock promptly; a follower acquires on its
next ``try_become_leader`` (bounded by the tick interval). The genuine overlap —
a dying leader's lock releasing mid-tick while a follower starts its own tick
concurrently — is made HARMLESS not by the lock but by the materialisation
**idempotency key**: both ticks compute the identical ``schedule_id+fire_time``
key, so A0's ``INSERT … ON CONFLICT DO NOTHING`` yields exactly one job per due
fire. The lock is a best-effort work-reducer; the key is the correctness
guarantee (T6 owns the materialisation).
"""

from __future__ import annotations

import contextlib
import zlib
from types import TracebackType
from typing import TYPE_CHECKING

from persona.logging import get_logger
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy import Engine
    from sqlalchemy.engine import Connection

__all__ = ["SCHEDULER_LEADER_LOCK_KEY", "SchedulerLeader"]

_log = get_logger("api.schedules.leadership")

# A stable 64-bit key for the scheduler-leader advisory lock. ``zlib.crc32`` is a
# fixed algorithm (deterministic ACROSS processes — unlike ``hash()``, which is
# per-process salted), so every worker computes the SAME key and they contend on
# the one lock. Namespaced by a distinctive string to avoid colliding with any
# other advisory-lock user's key space.
SCHEDULER_LEADER_LOCK_KEY: int = zlib.crc32(b"persona:scheduler:leader")


class SchedulerLeader:
    """Holds the scheduler-leader advisory lock on a dedicated session connection.

    Construct with an :class:`~sqlalchemy.Engine` (the worker's cross-tenant
    dispatch engine in production — advisory locks are not tenant data, so no
    RLS). Call :meth:`try_become_leader` each tick: it returns ``True`` while this
    worker holds the lock and acquires it if free. :meth:`resign` releases it.
    Re-entrant-safe: a worker already holding the lock does not re-lock.
    """

    def __init__(self, engine: Engine, *, lock_key: int = SCHEDULER_LEADER_LOCK_KEY) -> None:
        self._engine = engine
        self._lock_key = int(lock_key)
        # The held dedicated session connection while leader; None when a follower.
        self._conn: Connection | None = None

    @property
    def is_leader(self) -> bool:
        """True iff this worker currently holds the leadership lock."""
        return self._conn is not None

    def try_become_leader(self) -> bool:
        """Acquire (or confirm) leadership. Returns whether this worker is leader.

        Idempotent: if already leading on a live connection, returns ``True``
        without re-locking. If the held connection has died (crash of the DB-side
        session), it is dropped and a fresh acquisition is attempted — so a worker
        that silently lost the lock re-contends rather than ticking blind.
        """
        if self._conn is not None:
            if self._connection_alive(self._conn):
                return True
            # Lost the session under us — drop and re-contend below.
            self._drop()

        conn = self._engine.connect().execution_options(isolation_level="AUTOCOMMIT")
        try:
            acquired = bool(
                conn.execute(
                    text("SELECT pg_try_advisory_lock(:k)"), {"k": self._lock_key}
                ).scalar()
            )
        except Exception:
            conn.close()
            raise
        if acquired:
            self._conn = conn
            _log.info("acquired scheduler leadership", lock_key=self._lock_key)
            return True
        conn.close()
        return False

    def resign(self) -> None:
        """Release the lock + close the held connection. Idempotent.

        Called on graceful shutdown/drain. A best-effort unlock — if the
        connection is already dead, Postgres has released the session lock anyway,
        so the failure is swallowed.
        """
        conn = self._conn
        if conn is None:
            return
        with contextlib.suppress(Exception):
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": self._lock_key})
        self._drop()
        _log.info("resigned scheduler leadership", lock_key=self._lock_key)

    @staticmethod
    def _connection_alive(conn: Connection) -> bool:
        """A held connection is alive (and so the session lock is still held) iff
        a trivial probe succeeds. A dead session means Postgres released the lock."""
        try:
            conn.execute(text("SELECT 1"))
        except Exception:  # noqa: BLE001 — any failure means the session is gone
            return False
        return True

    def _drop(self) -> None:
        """Close + forget the held connection (no unlock). Best-effort."""
        if self._conn is not None:
            with contextlib.suppress(Exception):
                self._conn.close()
            self._conn = None

    def __enter__(self) -> SchedulerLeader:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.resign()

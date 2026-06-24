"""The durable schedule store — RLS-scoped CRUD + lifecycle (Spec A1, T4).

:class:`ScheduleStore` owns the durable side of A1's clock: it persists, reads,
edits, pauses/resumes, deletes, and records-fires-against schedules, all
**owner-scoped through RLS** (every operation runs inside the owner's
``app.current_user_id`` GUC via :func:`~persona_api.db.engine.rls_connection`),
so a cross-tenant reach hits zero rows — the standing adversarial guarantee.

Discipline held here:

* **CQS** — :meth:`get` / :meth:`list_for_owner` only read; the mutators only
  write and return the post-mutation :class:`~persona.schedules.Schedule` as the
  *confirmation* of the new state (the id/next-fire the caller needs), never a
  query result.
* **One ``AuditEvent`` per mutation** — exactly one ``audit_log`` row per
  create/edit/pause/resume/delete/fire (the project's auditability posture).
* **The ratified edit rule** — an edit recomputes ``next_fire_after(now)`` from
  the NEW rule but PRESERVES ``fire_count`` and ``created_at`` (the stable
  recurrence anchor), so there is no COUNT-reset loophole.
* **The next-fire invariant is centralised** — create/resume/edit/fire all set
  ``next_fire_at`` via the pure core :func:`~persona.schedules.next_fire_after`;
  no caller hand-computes it.

The cross-tenant scheduler tick (claiming due rows across owners, materialising
into A0 jobs) is a SEPARATE concern on the dispatch engine — T5/T6.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from persona.errors import ScheduleNotFoundError
from persona.logging import get_logger
from persona.schedules import RecurrenceRule, Schedule, next_fire_after
from sqlalchemy import delete, insert, select, update

from persona_api.db.engine import rls_connection
from persona_api.db.models import schedules as schedules_t
from persona_api.services import audit_service

if TYPE_CHECKING:
    from datetime import datetime

    from sqlalchemy import Engine, RowMapping

__all__ = ["ScheduleStore"]

_log = get_logger("api.schedules.store")

# The editable columns an edit may change. id / owner_id / created_at / fire_count
# / last_fire_at are preserved by the store (the ratified anchor + no COUNT reset);
# next_fire_at is recomputed, never caller-supplied.
_EDITABLE = (
    "timezone",
    "recurrence",
    "one_time_at",
    "target_job_type",
    "payload_template",
    "enabled",
    "paused",
    "missed_fire_policy",
    "grace_seconds",
)


def _recurrence_str(schedule: Schedule) -> str | None:
    """The RFC-5545 RRULE string for the durable column (None for a one-time)."""
    return schedule.recurrence.to_rrule_string() if schedule.recurrence is not None else None


def _row_to_schedule(row: RowMapping) -> Schedule:
    """Build a :class:`Schedule` from a ``schedules`` row (RRULE string → rule)."""
    recurrence_raw = row["recurrence"]
    recurrence = (
        RecurrenceRule.from_rrule_string(recurrence_raw) if recurrence_raw is not None else None
    )
    return Schedule(
        id=row["id"],
        owner_id=row["owner_id"],
        timezone=row["timezone"],
        recurrence=recurrence,
        one_time_at=row["one_time_at"],
        target_job_type=row["target_job_type"],
        payload_template=row["payload_template"],
        enabled=row["enabled"],
        paused=row["paused"],
        missed_fire_policy=row["missed_fire_policy"],
        grace_seconds=row["grace_seconds"],
        last_fire_at=row["last_fire_at"],
        next_fire_at=row["next_fire_at"],
        fire_count=row["fire_count"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _values(schedule: Schedule) -> dict[str, Any]:
    """The full column value map for an INSERT/UPDATE from a Schedule."""
    return {
        "id": schedule.id,
        "owner_id": schedule.owner_id,
        "timezone": schedule.timezone,
        "recurrence": _recurrence_str(schedule),
        "one_time_at": schedule.one_time_at,
        "target_job_type": schedule.target_job_type,
        "payload_template": dict(schedule.payload_template),
        "enabled": schedule.enabled,
        "paused": schedule.paused,
        "missed_fire_policy": schedule.missed_fire_policy.value,
        "grace_seconds": schedule.grace_seconds,
        "last_fire_at": schedule.last_fire_at,
        "next_fire_at": schedule.next_fire_at,
        "fire_count": schedule.fire_count,
        "created_at": schedule.created_at,
        "updated_at": schedule.updated_at,
    }


class ScheduleStore:
    """Owner-scoped, audited CRUD + lifecycle over the ``schedules`` table.

    Construct with the ``persona_app`` RLS engine — every operation re-binds the
    owner's GUC, so the store can never reach another tenant's rows. ``audit_log``
    (non-RLS, INSERT-only for ``persona_app``) carries the per-mutation event.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    # --- reads (CQS: no writes) --------------------------------------------

    def get(self, owner_id: str, schedule_id: str) -> Schedule:
        """Fetch one schedule. Raises :class:`ScheduleNotFoundError` on a miss.

        RLS-scoped: a cross-tenant id is indistinguishable from a missing one
        (both raise ``ScheduleNotFoundError`` — no existence oracle).
        """
        with rls_connection(self._engine, owner_id) as conn:
            row = (
                conn.execute(select(schedules_t).where(schedules_t.c.id == schedule_id))
                .mappings()
                .first()
            )
        if row is None:
            raise ScheduleNotFoundError("schedule not found", context={"schedule_id": schedule_id})
        return _row_to_schedule(row)

    def list_for_owner(self, owner_id: str) -> list[Schedule]:
        """All of the owner's schedules, newest first (RLS-scoped read)."""
        with rls_connection(self._engine, owner_id) as conn:
            rows = (
                conn.execute(select(schedules_t).order_by(schedules_t.c.created_at.desc()))
                .mappings()
                .all()
            )
        return [_row_to_schedule(r) for r in rows]

    # --- mutations (CQS: return the post-mutation state as confirmation) ----

    def create(self, schedule: Schedule, *, now: datetime) -> Schedule:
        """Persist a new schedule with its initial ``next_fire_at`` computed.

        The first fire is the next occurrence strictly after the creation anchor
        (``schedule.created_at``); the store sets it so the tick picks the row up.
        Audits ``schedule.create``.
        """
        first_fire = next_fire_after(schedule, after=schedule.created_at)
        stored = schedule.with_next_fire(first_fire, now=now)
        with rls_connection(self._engine, schedule.owner_id) as conn:
            conn.execute(insert(schedules_t).values(**_values(stored)))
        self._audit(schedule.owner_id, "schedule.create", stored)
        return stored

    def edit(self, proposed: Schedule, *, now: datetime) -> Schedule:
        """Apply an edit; recompute ``next_fire_at(now)``; PRESERVE the anchor.

        The ratified rule (no COUNT-reset loophole): ``created_at`` and
        ``fire_count`` (and ``last_fire_at``) are taken from the CURRENT row, not
        from ``proposed`` — so a rule change cannot restart the recurrence anchor
        or the fire budget. Only the editable fields move; ``next_fire_at`` is
        recomputed from the new rule as of ``now``. Audits ``schedule.edit``.
        """
        current = self.get(proposed.owner_id, proposed.id)
        merged = proposed.model_copy(
            update={
                "created_at": current.created_at,  # stable recurrence anchor
                "fire_count": current.fire_count,  # no COUNT reset
                "last_fire_at": current.last_fire_at,
            }
        )
        next_fire = next_fire_after(merged, after=now)
        merged = merged.with_next_fire(next_fire, now=now)
        self._update_or_raise(merged.owner_id, merged.id, _values(merged))
        self._audit(merged.owner_id, "schedule.edit", merged)
        return merged

    def pause(self, owner_id: str, schedule_id: str, *, now: datetime) -> Schedule:
        """Pause a schedule (stops firing, preserves the rule). Audits ``schedule.pause``.

        ``next_fire_at`` is left as-is; :meth:`resume` recomputes it so a long
        pause never fires a stale past time.
        """
        current = self.get(owner_id, schedule_id)
        paused = current.model_copy(update={"paused": True, "updated_at": now})
        self._update_or_raise(owner_id, schedule_id, {"paused": True, "updated_at": now})
        self._audit(owner_id, "schedule.pause", paused)
        return paused

    def resume(self, owner_id: str, schedule_id: str, *, now: datetime) -> Schedule:
        """Resume a paused schedule; recompute ``next_fire_at(now)``. Audits ``schedule.resume``.

        Recomputing from ``now`` (criterion 7) means a schedule resumed after a
        long pause fires next on its rhythm, not a stale missed instant.
        """
        current = self.get(owner_id, schedule_id)
        next_fire = next_fire_after(current, after=now)
        resumed = current.model_copy(
            update={"paused": False, "next_fire_at": next_fire, "updated_at": now}
        )
        self._update_or_raise(
            owner_id,
            schedule_id,
            {"paused": False, "next_fire_at": next_fire, "updated_at": now},
        )
        self._audit(owner_id, "schedule.resume", resumed)
        return resumed

    def record_fire(self, owner_id: str, schedule_id: str, *, fire_time: datetime) -> Schedule:
        """Record a fire, auto-advancing ``next_fire_at`` to the next occurrence.

        The new ``next_fire_at`` is the next occurrence strictly after
        ``fire_time`` (``None`` when the rule is exhausted or a one-time has fired
        — one-time COMPLETION). Audits ``schedule.fire``. For the tick's coalesced
        advance (next occurrence after *now*, the no-burst path), use
        :meth:`apply_fire` with an explicit ``next_fire_at``.
        """
        current = self.get(owner_id, schedule_id)
        next_fire = next_fire_after(current, after=fire_time)
        return self._persist_fire(owner_id, current, fire_time=fire_time, next_fire_at=next_fire)

    def apply_fire(
        self,
        owner_id: str,
        schedule_id: str,
        *,
        fire_time: datetime,
        next_fire_at: datetime | None,
        late: bool = False,
    ) -> Schedule:
        """Record a fire with an EXPLICIT ``next_fire_at`` (the tick's coalesce).

        The tick computes ``next_fire_at = next_fire_after(now)`` so a backlog of
        missed occurrences collapses to a single fire that jumps to the next
        FUTURE occurrence (the structural no-burst invariant), then records the
        fired scheduled instant via this method. ``late`` flags a fire-late-once
        catch-up: the durable note is ``schedule.fire_late`` (vs ``schedule.fire``)
        so A3/A6 can surface that the fire was a catch-up. A one-time schedule
        completes regardless (the entity forces ``None``).
        """
        current = self.get(owner_id, schedule_id)
        return self._persist_fire(
            owner_id, current, fire_time=fire_time, next_fire_at=next_fire_at, late=late
        )

    def skip_fire(
        self,
        owner_id: str,
        schedule_id: str,
        *,
        missed_fire_time: datetime,
        next_fire_at: datetime | None,
    ) -> Schedule:
        """Skip a missed fire: advance ``next_fire_at``, record a durable miss note.

        Used when the missed-fire policy declines to fire (skip-and-note, or
        fire-late-once beyond grace). It does NOT enqueue a job and does NOT bump
        ``fire_count`` (no fire happened); it only advances next-fire to the next
        future occurrence (the no-burst floor) and emits a durable ``schedule.miss``
        audit note (the missed scheduled instant) for A3 honesty / A6 display. A
        skipped one-time (``next_fire_at`` resolves to ``None``) terminates.
        """
        current = self.get(owner_id, schedule_id)
        updated = current.with_next_fire(next_fire_at, now=missed_fire_time)
        self._update_or_raise(
            owner_id,
            schedule_id,
            {"next_fire_at": next_fire_at, "updated_at": updated.updated_at},
        )
        self._audit(
            owner_id,
            "schedule.miss",
            updated,
            extra={"missed_fire_time": missed_fire_time.isoformat()},
        )
        return updated

    def _persist_fire(
        self,
        owner_id: str,
        current: Schedule,
        *,
        fire_time: datetime,
        next_fire_at: datetime | None,
        late: bool = False,
    ) -> Schedule:
        """Apply + persist + audit a fire on an already-fetched schedule."""
        fired = current.record_fire(fire_time=fire_time, next_fire_at=next_fire_at)
        self._update_or_raise(
            owner_id,
            current.id,
            {
                "fire_count": fired.fire_count,
                "last_fire_at": fired.last_fire_at,
                "next_fire_at": fired.next_fire_at,
                "updated_at": fired.updated_at,
            },
        )
        action = "schedule.fire_late" if late else "schedule.fire"
        self._audit(owner_id, action, fired, extra={"fire_time": fire_time.isoformat()})
        return fired

    def delete(self, owner_id: str, schedule_id: str) -> None:
        """Delete a schedule. Raises :class:`ScheduleNotFoundError` if absent.

        RLS-scoped: a cross-tenant delete affects zero rows and raises
        ``ScheduleNotFoundError`` (no oracle). CQS: returns nothing. Audits
        ``schedule.delete`` only on a real deletion.
        """
        with rls_connection(self._engine, owner_id) as conn:
            result = conn.execute(delete(schedules_t).where(schedules_t.c.id == schedule_id))
            if result.rowcount != 1:
                raise ScheduleNotFoundError(
                    "schedule not found", context={"schedule_id": schedule_id}
                )
        audit_service.record(
            engine=self._engine,
            user_id=owner_id,
            action="schedule.delete",
            target=schedule_id,
            metadata={},
        )

    # --- internals ----------------------------------------------------------

    def _update_or_raise(self, owner_id: str, schedule_id: str, values: dict[str, Any]) -> None:
        """RLS-scoped UPDATE of ``values``; raise NotFound if no row matched."""
        with rls_connection(self._engine, owner_id) as conn:
            result = conn.execute(
                update(schedules_t).where(schedules_t.c.id == schedule_id).values(**values)
            )
            if result.rowcount != 1:
                raise ScheduleNotFoundError(
                    "schedule not found", context={"schedule_id": schedule_id}
                )

    def _audit(
        self,
        owner_id: str,
        action: str,
        schedule: Schedule,
        *,
        extra: dict[str, str] | None = None,
    ) -> None:
        """Emit exactly one ``audit_log`` row for a schedule mutation.

        ``extra`` carries event-specific fields (e.g. the fired/missed scheduled
        instant) so the durable note is self-describing for A3 honesty / A6 display.
        """
        metadata: dict[str, str] = {
            "target_job_type": schedule.target_job_type,
            "fire_count": str(schedule.fire_count),
            "next_fire_at": schedule.next_fire_at.isoformat()
            if schedule.next_fire_at is not None
            else "",
        }
        if extra:
            metadata.update(extra)
        audit_service.record(
            engine=self._engine,
            user_id=owner_id,
            action=action,
            target=schedule.id,
            metadata=metadata,
        )

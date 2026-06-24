"""The missed-fire policy decision (Spec A1, T7) — pure, on top of no-burst.

When the tick finds a due fire, it asks ONE pure question: given how late this
fire is, the schedule's policy, and its grace window — do we fire it, fire it as
a late catch-up, or skip it and note the miss? This is the POLICY layer on top of
the structural no-burst floor (the tick always advances ``next_fire_after(now)``
regardless of the decision — D-A1-2), so a backlog can never replay.

The model (D-A1-2), matching mature schedulers (APScheduler ``misfire_grace_time``
+ ``coalesce``):

* **on time** — caught within ``on_time_tolerance`` of the scheduled instant (the
  worker was up; this is the normal case) → ``FIRE`` regardless of policy.
* **late, FIRE_LATE_ONCE, within grace** → ``FIRE_LATE`` (a single catch-up, then
  the rhythm resumes — the no-burst floor handles "single").
* **late, beyond grace (FIRE_LATE_ONCE) OR any late under SKIP_AND_NOTE** → ``SKIP``
  (don't fire; the tick records a durable miss note and advances).

``SKIP_AND_NOTE`` never catches up — a missed occurrence is recorded and the next
regular fire proceeds. Pure + exhaustively unit-tested; no clock, no I/O.
"""

from __future__ import annotations

from enum import StrEnum

from persona.schedules.models import MissedFirePolicy

__all__ = ["FireAction", "decide_fire"]


class FireAction(StrEnum):
    """The tick's decision for one due fire.

    ``FIRE`` — materialise an on-time fire; ``FIRE_LATE`` — materialise a late
    catch-up (fire-late-once within grace), noted as late; ``SKIP`` — do not fire,
    record a durable miss note. In every case the tick advances next-fire to the
    next future occurrence (the no-burst floor).
    """

    FIRE = "fire"
    FIRE_LATE = "fire-late"
    SKIP = "skip"


def decide_fire(
    *,
    policy: MissedFirePolicy,
    lateness_seconds: float,
    grace_seconds: float,
    on_time_tolerance_seconds: float,
) -> FireAction:
    """Decide what to do with a due fire that is ``lateness_seconds`` late.

    Args:
        policy: The schedule's missed-fire policy.
        lateness_seconds: ``now - scheduled_fire_time`` in seconds (``>= 0`` — the
            tick only claims fires that are due).
        grace_seconds: How late a missed fire may be and still be caught up
            (fire-late-once). Per-schedule override or the kind-relative default.
        on_time_tolerance_seconds: How late still counts as "caught promptly" (the
            worker was up — the normal next-tick latency), firing regardless of
            policy. Guards against treating tick jitter as a miss.

    Returns:
        The :class:`FireAction` to take.
    """
    if lateness_seconds <= on_time_tolerance_seconds:
        return FireAction.FIRE
    if policy is MissedFirePolicy.FIRE_LATE_ONCE and lateness_seconds <= grace_seconds:
        return FireAction.FIRE_LATE
    return FireAction.SKIP

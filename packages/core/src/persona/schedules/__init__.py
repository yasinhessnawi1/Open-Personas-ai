"""persona.schedules — the durable schedule contract (Spec A1, scheduling).

persona-core owns the schedule entity + the RRULE-class recurrence model + the
pure, DST-correct next-fire computation (T2); the durable RLS-scoped store and
the single-leader tick (persona-api) compose them. A1 is the clock: "every
morning at 7" means the user's 7, reliably, forever — the timezone lives on the
schedule, and each due fire materialises into an A0 job keyed by
``schedule_id + fire_time`` (riding A0's effectively-once, not reinventing it).

See ``docs/specs/phase3/spec_A1/`` for the spec, decisions, and research.
"""

from __future__ import annotations

from persona.schedules.keys import (
    FIRE_PAYLOAD_FIRE_TIME_KEY,
    FIRE_PAYLOAD_SCHEDULE_ID_KEY,
    fire_idempotency_key,
    fire_payload,
)
from persona.schedules.models import (
    MissedFirePolicy,
    RecurrenceFreq,
    RecurrenceRule,
    Schedule,
)
from persona.schedules.nextfire import next_fire_after
from persona.schedules.policy import FireAction, decide_fire

__all__ = [
    "FIRE_PAYLOAD_FIRE_TIME_KEY",
    "FIRE_PAYLOAD_SCHEDULE_ID_KEY",
    "FireAction",
    "MissedFirePolicy",
    "RecurrenceFreq",
    "RecurrenceRule",
    "Schedule",
    "decide_fire",
    "fire_idempotency_key",
    "fire_payload",
    "next_fire_after",
]

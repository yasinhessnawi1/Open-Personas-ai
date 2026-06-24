"""The schedule-fire idempotency-key + handoff-payload contract (Spec A1).

A1 rides A0's effectively-once guarantee rather than reinventing it
(D-A1-X-idempotency-key): each due fire materialises into an A0 job whose
idempotency key is **deterministic in ``(schedule_id, fire_time)``**, so a double
tick, a leader handover mid-tick, or a crash-rerun all dedup — via A0's
``INSERT … ON CONFLICT (owner_id, idempotency_key) DO NOTHING`` — to exactly one
job per due fire. The fired job's payload carries the schedule identity + fire
time (the handoff contract, criterion 8) so a downstream leg can anchor "which
morning is this." These are pure contract helpers (no I/O), shared by the tick
(persona-api) and any downstream consumer.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from datetime import datetime

__all__ = ["FIRE_PAYLOAD_FIRE_TIME_KEY", "FIRE_PAYLOAD_SCHEDULE_ID_KEY", "fire_idempotency_key"]

# The payload keys the tick stamps onto every fired job (the handoff anchor). A
# downstream leg reads these to know which schedule + which scheduled instant
# this run belongs to. Stable strings so producer and consumer agree.
FIRE_PAYLOAD_SCHEDULE_ID_KEY = "schedule_id"
FIRE_PAYLOAD_FIRE_TIME_KEY = "fire_time"


def fire_idempotency_key(schedule_id: str, fire_time: datetime) -> str:
    """The deterministic A0 idempotency key for one ``(schedule, fire_time)`` fire.

    ``sched:{schedule_id}:{fire_time}`` with ``fire_time`` as its canonical UTC
    ISO-8601 instant — stable regardless of which worker computes it, so two
    overlapping ticks produce the IDENTICAL key and A0 dedups to one job. The
    ``fire_time`` is normalised to UTC ISO (the scheduled instant, even if fired
    late) so the key is byte-stable.
    """
    return f"sched:{schedule_id}:{fire_time.isoformat()}"


def fire_payload(
    schedule_id: str, fire_time: datetime, template: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Build a fired job's payload: the template + the handoff anchor.

    The schedule's configured ``payload_template`` (if any) is merged with the
    handoff fields (``schedule_id`` + ``fire_time``), which always win so the
    anchor can never be shadowed by a template key.
    """
    payload: dict[str, Any] = dict(template) if template else {}
    payload[FIRE_PAYLOAD_SCHEDULE_ID_KEY] = schedule_id
    payload[FIRE_PAYLOAD_FIRE_TIME_KEY] = fire_time.isoformat()
    return payload

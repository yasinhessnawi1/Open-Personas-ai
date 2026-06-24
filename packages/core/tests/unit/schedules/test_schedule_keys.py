"""Unit tests for the schedule-fire key + handoff-payload contract (Spec A1, T6)."""

from __future__ import annotations

from datetime import UTC, datetime

from persona.schedules import (
    FIRE_PAYLOAD_FIRE_TIME_KEY,
    FIRE_PAYLOAD_SCHEDULE_ID_KEY,
    fire_idempotency_key,
)
from persona.schedules.keys import fire_payload

_FIRE = datetime(2026, 3, 10, 11, 0, tzinfo=UTC)


def test_idempotency_key_is_deterministic_in_schedule_and_fire_time() -> None:
    k1 = fire_idempotency_key("sched-1", _FIRE)
    k2 = fire_idempotency_key("sched-1", _FIRE)
    assert k1 == k2 == f"sched:sched-1:{_FIRE.isoformat()}"


def test_idempotency_key_differs_per_fire_time() -> None:
    later = datetime(2026, 3, 11, 11, 0, tzinfo=UTC)
    assert fire_idempotency_key("sched-1", _FIRE) != fire_idempotency_key("sched-1", later)


def test_idempotency_key_differs_per_schedule() -> None:
    assert fire_idempotency_key("a", _FIRE) != fire_idempotency_key("b", _FIRE)


def test_fire_payload_carries_the_handoff_anchor() -> None:
    payload = fire_payload("sched-1", _FIRE)
    assert payload[FIRE_PAYLOAD_SCHEDULE_ID_KEY] == "sched-1"
    assert payload[FIRE_PAYLOAD_FIRE_TIME_KEY] == _FIRE.isoformat()


def test_fire_payload_merges_template_but_anchor_wins() -> None:
    template = {"kind": "morning", "schedule_id": "SPOOFED"}
    payload = fire_payload("sched-1", _FIRE, template)
    assert payload["kind"] == "morning"  # template preserved
    assert payload[FIRE_PAYLOAD_SCHEDULE_ID_KEY] == "sched-1"  # anchor cannot be shadowed


def test_fire_payload_does_not_mutate_the_template() -> None:
    template = {"kind": "morning"}
    fire_payload("sched-1", _FIRE, template)
    assert template == {"kind": "morning"}  # caller's dict untouched

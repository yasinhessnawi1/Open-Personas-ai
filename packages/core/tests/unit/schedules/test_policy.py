"""Unit tests for the missed-fire policy decision (Spec A1, T7)."""

from __future__ import annotations

import pytest
from persona.schedules import FireAction, MissedFirePolicy, decide_fire

_GRACE = 10_800.0  # 3h
_TOL = 120.0  # 2min on-time tolerance


@pytest.mark.parametrize("policy", list(MissedFirePolicy))
def test_on_time_fire_fires_regardless_of_policy(policy: MissedFirePolicy) -> None:
    # Caught within the on-time tolerance → a normal fire, both policies.
    assert (
        decide_fire(
            policy=policy,
            lateness_seconds=30.0,
            grace_seconds=_GRACE,
            on_time_tolerance_seconds=_TOL,
        )
        is FireAction.FIRE
    )


def test_on_time_boundary_is_inclusive() -> None:
    assert (
        decide_fire(
            policy=MissedFirePolicy.SKIP_AND_NOTE,
            lateness_seconds=_TOL,  # exactly at tolerance → still on-time
            grace_seconds=_GRACE,
            on_time_tolerance_seconds=_TOL,
        )
        is FireAction.FIRE
    )


def test_fire_late_once_within_grace_catches_up() -> None:
    assert (
        decide_fire(
            policy=MissedFirePolicy.FIRE_LATE_ONCE,
            lateness_seconds=1_800.0,  # 30min late, well within 3h grace
            grace_seconds=_GRACE,
            on_time_tolerance_seconds=_TOL,
        )
        is FireAction.FIRE_LATE
    )


def test_fire_late_once_at_grace_boundary_still_catches_up() -> None:
    assert (
        decide_fire(
            policy=MissedFirePolicy.FIRE_LATE_ONCE,
            lateness_seconds=_GRACE,  # exactly at grace → still caught up
            grace_seconds=_GRACE,
            on_time_tolerance_seconds=_TOL,
        )
        is FireAction.FIRE_LATE
    )


def test_fire_late_once_beyond_grace_skips() -> None:
    assert (
        decide_fire(
            policy=MissedFirePolicy.FIRE_LATE_ONCE,
            lateness_seconds=_GRACE + 1,  # 3h+ late → past grace, skip + note
            grace_seconds=_GRACE,
            on_time_tolerance_seconds=_TOL,
        )
        is FireAction.SKIP
    )


def test_skip_and_note_never_catches_up_even_within_grace() -> None:
    # A late fire under skip-and-note is skipped even though it is within what
    # would be a fire-late grace window — skip-and-note never catches up.
    assert (
        decide_fire(
            policy=MissedFirePolicy.SKIP_AND_NOTE,
            lateness_seconds=1_800.0,  # 30min late, < grace
            grace_seconds=_GRACE,
            on_time_tolerance_seconds=_TOL,
        )
        is FireAction.SKIP
    )

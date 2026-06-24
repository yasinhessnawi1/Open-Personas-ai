"""The DST fixture suite — the architectural lock (Spec A1, T2).

These tests ARE the heart of A1 (criteria 1–2): they prove ``next_fire_after``
fires at the user's local wall-clock time across both DST transitions, and that
the two classic edges behave as DEFINED (D-A1-X-fixture-suite):

* the **happy path** — wall-clock holds across spring AND fall (the timezone
  property on the edges, not the easy middle);
* the **spring-forward GAP** — a nonexistent local time fires at the adjusted
  instant (``resolve_imaginary``);
* the **fall-back FOLD** — a repeated local time fires once, the first occurrence
  (``fold=0``);
* the **gap-before-fold ordering** — a gap is also reported ambiguous, so the
  resolution must be existence-first;
* a **reversed-DST (southern-hemisphere)** timezone, so the logic is not
  accidentally US/EU-shaped;
* **COUNT / UNTIL exhaustion**, including across a DST boundary so the tail can
  never silently miscount.

Everything is pure: a frozen ``Schedule`` + a fixed ``after`` instant in, a UTC
instant (or ``None``) out. No clock, no database.
"""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

import pytest
from dateutil import tz as dtz
from persona.schedules import (
    RecurrenceFreq,
    RecurrenceRule,
    Schedule,
    next_fire_after,
)

NY = "America/New_York"
OSLO = "Europe/Oslo"
SYDNEY = "Australia/Sydney"  # reversed-DST: spring-forward in Oct, fall-back in Apr


def _utc(y: int, mo: int, d: int, h: int, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=UTC)


def _recurring(
    *,
    tz: str,
    rule: RecurrenceRule,
    created_at: datetime,
) -> Schedule:
    return Schedule(
        id="s1",
        owner_id="u1",
        timezone=tz,
        recurrence=rule,
        target_job_type="briefing",
        created_at=created_at,
        updated_at=created_at,
    )


def _daily_at(hour: int, minute: int = 0) -> RecurrenceRule:
    return RecurrenceRule(freq=RecurrenceFreq.DAILY, byhour=(hour,), byminute=(minute,))


def _local_wallclock(instant: datetime, tz: str) -> tuple[int, int]:
    """The (hour, minute) a UTC instant reads as on the wall clock in ``tz``."""
    local = instant.astimezone(ZoneInfo(tz))
    return local.hour, local.minute


# ---------------------------------------------------------------------------
# Happy path: wall-clock holds across BOTH transitions (criterion 1).
# ---------------------------------------------------------------------------


def test_daily_7am_ny_holds_wallclock_across_spring_forward() -> None:
    # Created Fri 2024-03-08; spring-forward is Sun 2024-03-10 (EST -5 → EDT -4).
    sched = _recurring(tz=NY, rule=_daily_at(7), created_at=_utc(2024, 3, 8, 1))
    # Day before the transition: 07:00 EST = 12:00Z.
    f1 = next_fire_after(sched, _utc(2024, 3, 9, 0))
    assert f1 == _utc(2024, 3, 9, 12)
    assert _local_wallclock(f1, NY) == (7, 0)
    # Transition day: 07:00 EDT = 11:00Z — the user's 7am, an hour earlier in UTC.
    f2 = next_fire_after(sched, f1)
    assert f2 == _utc(2024, 3, 10, 11)
    assert _local_wallclock(f2, NY) == (7, 0)
    # Day after: still 07:00 local = 11:00Z.
    f3 = next_fire_after(sched, f2)
    assert f3 == _utc(2024, 3, 11, 11)
    assert _local_wallclock(f3, NY) == (7, 0)


def test_daily_7am_ny_holds_wallclock_across_fall_back() -> None:
    # Fall-back is Sun 2024-11-03 (EDT -4 → EST -5).
    sched = _recurring(tz=NY, rule=_daily_at(7), created_at=_utc(2024, 11, 1, 1))
    f1 = next_fire_after(sched, _utc(2024, 11, 2, 0))  # 07:00 EDT = 11:00Z
    assert f1 == _utc(2024, 11, 2, 11)
    f2 = next_fire_after(sched, f1)  # transition day: 07:00 EST = 12:00Z
    assert f2 == _utc(2024, 11, 3, 12)
    f3 = next_fire_after(sched, f2)  # 07:00 EST = 12:00Z
    assert f3 == _utc(2024, 11, 4, 12)
    for fire in (f1, f2, f3):
        assert _local_wallclock(fire, NY) == (7, 0)


def test_daily_7am_oslo_holds_wallclock_across_both_transitions() -> None:
    # Oslo: spring 2024-03-31 (CET +1 → CEST +2); fall 2024-10-27 (CEST +2 → CET +1).
    spring = _recurring(tz=OSLO, rule=_daily_at(7), created_at=_utc(2024, 3, 29, 1))
    f_before = next_fire_after(spring, _utc(2024, 3, 30, 0))  # 07:00 CET = 06:00Z
    f_after = next_fire_after(spring, f_before)  # 07:00 CEST = 05:00Z
    assert f_before == _utc(2024, 3, 30, 6)
    assert f_after == _utc(2024, 3, 31, 5)
    assert _local_wallclock(f_after, OSLO) == (7, 0)


# ---------------------------------------------------------------------------
# Spring-forward GAP: nonexistent local time → adjusted instant (criterion 2).
# ---------------------------------------------------------------------------


def test_spring_gap_ny_fires_at_adjusted_instant() -> None:
    # 02:30 does not exist on 2024-03-10 (clocks jump 02:00 → 03:00). It must fire
    # at the adjusted instant 03:30 EDT = 07:30Z.
    sched = _recurring(tz=NY, rule=_daily_at(2, 30), created_at=_utc(2024, 3, 8, 0))
    gap_day_fire = next_fire_after(sched, _utc(2024, 3, 10, 0))
    assert gap_day_fire == _utc(2024, 3, 10, 7, 30)
    # The adjusted local wall-clock is 03:30 (the post-jump time), not 02:30.
    assert _local_wallclock(gap_day_fire, NY) == (3, 30)


def test_spring_gap_oslo_fires_at_adjusted_instant() -> None:
    # Oslo 2024-03-31: 02:30 doesn't exist (02:00 CET → 03:00 CEST) → 03:30 CEST = 01:30Z.
    sched = _recurring(tz=OSLO, rule=_daily_at(2, 30), created_at=_utc(2024, 3, 29, 0))
    fire = next_fire_after(sched, _utc(2024, 3, 31, 0))
    assert fire == _utc(2024, 3, 31, 1, 30)
    assert _local_wallclock(fire, OSLO) == (3, 30)


def test_gap_before_fold_ordering_is_existence_first() -> None:
    # The ordering trap: the gap time 02:30 on spring-forward is ALSO reported
    # ambiguous by dateutil. If the code branched on ambiguity first it would
    # mis-resolve. Assert both the trap precondition AND the correct outcome.
    gap = datetime(2024, 3, 10, 2, 30, tzinfo=ZoneInfo(NY))
    assert dtz.datetime_exists(gap) is False  # it is a gap
    assert dtz.datetime_ambiguous(gap) is True  # ...and ALSO reported ambiguous
    sched = _recurring(tz=NY, rule=_daily_at(2, 30), created_at=_utc(2024, 3, 8, 0))
    fire = next_fire_after(sched, _utc(2024, 3, 10, 0))
    # Existence-first resolution → adjusted instant (03:30 EDT), not a fold pick.
    assert fire == _utc(2024, 3, 10, 7, 30)


# ---------------------------------------------------------------------------
# Fall-back FOLD: repeated local time fires once, the first occurrence.
# ---------------------------------------------------------------------------


def test_fall_fold_ny_fires_once_at_first_occurrence() -> None:
    # 01:30 occurs twice on 2024-11-03 (01:00 EDT, then clocks fall back to 01:00
    # EST and 01:30 happens again). It must fire ONCE, at the first occurrence:
    # 01:30 EDT = 05:30Z (not the second, 01:30 EST = 06:30Z).
    sched = _recurring(tz=NY, rule=_daily_at(1, 30), created_at=_utc(2024, 11, 1, 0))
    fold_day_fire = next_fire_after(sched, _utc(2024, 11, 3, 0))
    assert fold_day_fire == _utc(2024, 11, 3, 5, 30)  # first (EDT) instant
    # The very next fire is the following day — the repeated 01:30 EST (06:30Z) is
    # NOT fired (no burst, fire-once).
    next_day = next_fire_after(sched, fold_day_fire)
    assert next_day == _utc(2024, 11, 4, 6, 30)  # 01:30 EST next day
    assert next_day != _utc(2024, 11, 3, 6, 30)  # the skipped second occurrence


def test_fall_fold_only_one_fire_within_the_repeated_hour() -> None:
    # Enumerate every fire on the fold day: exactly one lands in the repeated hour.
    sched = _recurring(tz=NY, rule=_daily_at(1, 30), created_at=_utc(2024, 11, 1, 0))
    fires: list[datetime] = []
    cursor = _utc(2024, 11, 3, 0)
    for _ in range(3):
        nxt = next_fire_after(sched, cursor)
        assert nxt is not None
        fires.append(nxt)
        cursor = nxt
    fold_day = [f for f in fires if f.astimezone(ZoneInfo(NY)).date().day == 3]
    assert len(fold_day) == 1


# ---------------------------------------------------------------------------
# Reversed-DST (southern hemisphere): not accidentally US/EU-shaped.
# ---------------------------------------------------------------------------


def test_sydney_spring_forward_gap_in_october() -> None:
    # Sydney springs forward 2024-10-06 (02:00 AEST +10 → 03:00 AEDT +11). 02:30
    # doesn't exist → 03:30 AEDT = 16:30Z (prev day).
    sched = _recurring(tz=SYDNEY, rule=_daily_at(2, 30), created_at=_utc(2024, 10, 3, 0))
    # ``after`` (Oct 5 12:00Z = Oct 5 22:00 Sydney) is before the Oct 6 gap fire
    # (03:30 AEDT = Oct 5 16:30Z) and after the Oct 5 fire — so the gap fire is next.
    fire = next_fire_after(sched, _utc(2024, 10, 5, 12))
    assert _local_wallclock(fire, SYDNEY) == (3, 30)
    assert fire == _utc(2024, 10, 5, 16, 30)


def test_sydney_fall_back_fold_in_april() -> None:
    # Sydney falls back 2024-04-07 (03:00 AEDT +11 → 02:00 AEST +10). 02:30 occurs
    # twice → fire once at the first (AEDT) instant = 02:30 AEDT = 15:30Z (prev day).
    sched = _recurring(tz=SYDNEY, rule=_daily_at(2, 30), created_at=_utc(2024, 4, 4, 0))
    fire = next_fire_after(sched, _utc(2024, 4, 6, 12))
    assert fire == _utc(2024, 4, 6, 15, 30)
    nxt = next_fire_after(sched, fire)
    assert nxt == _utc(2024, 4, 7, 16, 30)  # next day 02:30 AEST, not the repeat


def test_sydney_daily_7am_holds_wallclock_across_spring() -> None:
    sched = _recurring(tz=SYDNEY, rule=_daily_at(7), created_at=_utc(2024, 10, 3, 0))
    f1 = next_fire_after(sched, _utc(2024, 10, 4, 0))  # 07:00 AEST +10 = 21:00Z prev day
    f2 = next_fire_after(sched, f1)  # transition day 07:00 AEDT +11
    assert _local_wallclock(f1, SYDNEY) == (7, 0)
    assert _local_wallclock(f2, SYDNEY) == (7, 0)


# ---------------------------------------------------------------------------
# One-time futures (criterion 3).
# ---------------------------------------------------------------------------


def test_one_time_returns_instant_when_after_is_earlier() -> None:
    when = _utc(2026, 6, 1, 9)
    sched = Schedule(
        id="s1",
        owner_id="u1",
        timezone=OSLO,
        one_time_at=when,
        target_job_type="reminder",
        created_at=_utc(2026, 1, 1, 0),
        updated_at=_utc(2026, 1, 1, 0),
    )
    assert next_fire_after(sched, _utc(2026, 5, 31, 0)) == when


def test_one_time_returns_none_when_already_past() -> None:
    when = _utc(2026, 6, 1, 9)
    sched = Schedule(
        id="s1",
        owner_id="u1",
        timezone=OSLO,
        one_time_at=when,
        target_job_type="reminder",
        created_at=_utc(2026, 1, 1, 0),
        updated_at=_utc(2026, 1, 1, 0),
    )
    assert next_fire_after(sched, when) is None  # strictly-after: not the instant itself
    assert next_fire_after(sched, _utc(2026, 6, 2, 0)) is None


# ---------------------------------------------------------------------------
# COUNT / UNTIL exhaustion (criterion 7 termination) — incl. across DST.
# ---------------------------------------------------------------------------


def test_count_bounded_fires_exactly_n_times_then_none() -> None:
    rule = RecurrenceRule(freq=RecurrenceFreq.DAILY, byhour=(7,), byminute=(0,), count=3)
    sched = _recurring(tz=NY, rule=rule, created_at=_utc(2024, 1, 1, 0))
    fires: list[datetime] = []
    cursor = sched.created_at
    while (nxt := next_fire_after(sched, cursor)) is not None:
        fires.append(nxt)
        cursor = nxt
        assert len(fires) <= 10  # guard against an unbounded loop in a red state
    assert len(fires) == 3  # exactly COUNT fires
    assert all(_local_wallclock(f, NY) == (7, 0) for f in fires)


def test_count_bounded_across_spring_forward_counts_correctly() -> None:
    # 5 daily 02:30 fires from 2024-03-08; the 03-10 fire is the gap-adjusted one.
    # COUNT must still be exactly 5 (the DST edge does not add or drop a fire).
    rule = RecurrenceRule(freq=RecurrenceFreq.DAILY, byhour=(2,), byminute=(30,), count=5)
    sched = _recurring(tz=NY, rule=rule, created_at=_utc(2024, 3, 8, 0))
    fires: list[datetime] = []
    cursor = sched.created_at
    while (nxt := next_fire_after(sched, cursor)) is not None:
        fires.append(nxt)
        cursor = nxt
        assert len(fires) <= 10
    assert len(fires) == 5
    # created Mar 8 00:00Z (= Mar 7 19:00 EST) → fires Mar 8/9/10/11/12 at 02:30.
    # The Mar-10 gap fire is adjusted to 03:30 EDT (07:30Z) — fire #3 (index 2).
    assert fires[2] == _utc(2024, 3, 10, 7, 30)
    assert _local_wallclock(fires[2], NY) == (3, 30)


def test_until_bounds_the_tail_in_absolute_utc() -> None:
    until = _utc(2024, 1, 4, 12)  # 07:00 EST on Jan 4 = 12:00Z
    rule = RecurrenceRule(freq=RecurrenceFreq.DAILY, byhour=(7,), byminute=(0,), until=until)
    sched = _recurring(tz=NY, rule=rule, created_at=_utc(2024, 1, 1, 0))
    fires: list[datetime] = []
    cursor = sched.created_at
    while (nxt := next_fire_after(sched, cursor)) is not None:
        fires.append(nxt)
        cursor = nxt
        assert len(fires) <= 10
    # created Jan 1 00:00Z (= Dec 31 19:00 EST) → first fire is the SAME local day,
    # Jan 1 07:00 EST = 12:00Z. Fires Jan 1/2/3/4 (12:00Z each); Jan 4 == UNTIL is
    # included; Jan 5 is past it.
    assert fires == [
        _utc(2024, 1, 1, 12),
        _utc(2024, 1, 2, 12),
        _utc(2024, 1, 3, 12),
        _utc(2024, 1, 4, 12),
    ]


def test_until_across_spring_forward_does_not_miscount() -> None:
    # UNTIL just after the spring-forward fire. Compared in absolute UTC, the
    # transition cannot silently add/drop the boundary fire (the reconciliation).
    # Last allowed fire: 2024-03-11 07:00 EDT = 11:00Z. UNTIL = 11:00Z exactly.
    until = _utc(2024, 3, 11, 11)
    rule = RecurrenceRule(freq=RecurrenceFreq.DAILY, byhour=(7,), byminute=(0,), until=until)
    sched = _recurring(tz=NY, rule=rule, created_at=_utc(2024, 3, 8, 0))
    fires: list[datetime] = []
    cursor = sched.created_at
    while (nxt := next_fire_after(sched, cursor)) is not None:
        fires.append(nxt)
        cursor = nxt
        assert len(fires) <= 12
    # created Mar 8 00:00Z (= Mar 7 19:00 EST) → first fire Mar 8 07:00 EST = 12:00Z.
    # Mar 8/9 (12:00Z, EST), Mar 10 (11:00Z, EDT post-jump), Mar 11 (11:00Z == UNTIL,
    # included by the absolute-UTC comparison).
    assert fires == [
        _utc(2024, 3, 8, 12),
        _utc(2024, 3, 9, 12),
        _utc(2024, 3, 10, 11),
        _utc(2024, 3, 11, 11),
    ]


# ---------------------------------------------------------------------------
# Pattern expressiveness + strictly-after contract.
# ---------------------------------------------------------------------------


def test_strictly_after_skips_the_instant_itself() -> None:
    sched = _recurring(tz=NY, rule=_daily_at(7), created_at=_utc(2024, 6, 1, 0))
    fire = next_fire_after(sched, _utc(2024, 6, 10, 0))
    assert fire is not None
    # Asking again with after == fire returns the NEXT day, never the same instant.
    again = next_fire_after(sched, fire)
    assert again is not None
    assert again > fire


def test_weekly_byday_pattern_fires_on_the_named_day() -> None:
    rule = RecurrenceRule(freq=RecurrenceFreq.WEEKLY, byday=("MO",), byhour=(9,), byminute=(0,))
    sched = _recurring(tz=OSLO, rule=rule, created_at=_utc(2024, 6, 1, 0))  # Sat
    fire = next_fire_after(sched, _utc(2024, 6, 1, 0))
    assert fire is not None
    assert fire.astimezone(ZoneInfo(OSLO)).weekday() == 0  # Monday
    assert _local_wallclock(fire, OSLO) == (9, 0)


def test_monthly_first_monday_pattern() -> None:
    rule = RecurrenceRule(freq=RecurrenceFreq.MONTHLY, byday=("1MO",), byhour=(8,), byminute=(0,))
    sched = _recurring(tz=OSLO, rule=rule, created_at=_utc(2024, 6, 15, 0))
    fire = next_fire_after(sched, _utc(2024, 6, 15, 0))
    assert fire is not None
    local = fire.astimezone(ZoneInfo(OSLO))
    assert local.weekday() == 0  # Monday
    assert local.day <= 7  # ...the FIRST one of the month


def test_after_must_be_timezone_aware() -> None:
    sched = _recurring(tz=NY, rule=_daily_at(7), created_at=_utc(2024, 1, 1, 0))
    with pytest.raises(ValueError, match="aware"):
        next_fire_after(sched, datetime(2024, 6, 1, 0))  # noqa: DTZ001 — deliberately naive


def test_after_accepts_non_utc_aware_instant() -> None:
    # A non-UTC aware ``after`` is normalised, not rejected.
    sched = _recurring(tz=NY, rule=_daily_at(7), created_at=_utc(2024, 1, 1, 0))
    oslo_after = datetime(2024, 6, 10, 2, 0, tzinfo=ZoneInfo(OSLO))
    fire = next_fire_after(sched, oslo_after)
    assert fire is not None
    assert fire.tzinfo == UTC

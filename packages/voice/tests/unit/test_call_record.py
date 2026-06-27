"""Unit tests for the durable call-record writer (Spec V9, V9-D-5).

Drives :class:`CallRecorder` over an in-memory SQLite engine carrying core's own
``calls`` Table view — proving the open→insert / close→finalize SQL + the stored
duration without a Postgres dependency — plus the best-effort contract (a write
failure MUST NOT raise, mirroring the episodic write in
:mod:`persona_voice.model.memory`).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from persona.calls import calls as _calls
from persona_voice.session.call_record import CallRecorder
from sqlalchemy import Engine, create_engine, select


def _sqlite_engine() -> Engine:
    """An in-memory engine carrying core's ``calls`` view (no Postgres / RLS)."""
    engine = create_engine("sqlite://")
    _calls.metadata.create_all(engine)
    return engine


def _recorder(engine: Engine, *, clock: Callable[[], datetime] | None = None) -> CallRecorder:
    return CallRecorder(
        engine=engine,
        call_id="call_x",
        conversation_id="c1",
        persona_id="p1",
        owner_id="u1",
        clock=clock,
    )


class TestCallRecorderHappyPath:
    def test_open_inserts_a_live_record(self) -> None:
        engine = _sqlite_engine()
        t0 = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)
        _recorder(engine, clock=lambda: t0).open()

        with engine.begin() as conn:
            row = conn.execute(select(_calls)).one()
        assert row.call_id == "call_x"
        assert row.conversation_id == "c1"
        assert row.persona_id == "p1"
        assert row.owner_id == "u1"
        assert row.started_at is not None
        # live: not yet finalized.
        assert row.ended_at is None
        assert row.duration_s is None
        assert row.end_reason is None

    def test_close_finalizes_with_stored_duration_and_reason(self) -> None:
        engine = _sqlite_engine()
        t0 = datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC)
        recorder = _recorder(engine, clock=lambda: t0)
        recorder.open(t0)
        recorder.close(end_reason="disconnect", ended_at=t0 + timedelta(seconds=125))

        with engine.begin() as conn:
            row = conn.execute(select(_calls)).one()
        assert row.ended_at is not None
        # duration is STORED (V9-D-5), computed in Python from started_at.
        assert row.duration_s == 125
        assert row.end_reason == "disconnect"

    def test_close_without_open_records_null_duration(self) -> None:
        """If open() never ran (e.g. it failed), close() still finalizes — the
        UPDATE matches nothing, so this is a safe no-op; duration is unknown."""
        engine = _sqlite_engine()
        recorder = _recorder(engine)
        recorder.close(end_reason="error")  # must not raise
        with engine.begin() as conn:
            assert conn.execute(select(_calls)).first() is None


class TestCallRecorderFailSoft:
    """A persistence failure degrades the call-record, never the call (the V4
    ``finally`` discipline — close() runs in the suppressed teardown path)."""

    def test_open_and_close_do_not_raise_on_db_error(self) -> None:
        # An engine with NO ``calls`` table → every write raises "no such table",
        # which the recorder must swallow (best-effort, like the episodic write).
        engine = create_engine("sqlite://")
        recorder = _recorder(engine)
        recorder.open()  # must not raise
        recorder.close(end_reason="disconnect")  # must not raise

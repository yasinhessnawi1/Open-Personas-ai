"""Unit test for the voice transcript writer's fail-soft contract (V9-D-2).

The happy-path byte-for-byte write is proven against a real Postgres + the api
read surface in the api integration suite (``test_conversations`` —
``test_voice_turn_persists_to_messages_and_renders``). Here we lock the
best-effort discipline in isolation: a DB error during the write MUST NOT raise
(``record_turn`` runs in V4's turn-commit ``finally`` — a transcript-write
failure degrades the saved transcript, never the live call).
"""

from __future__ import annotations

from datetime import UTC, datetime

from persona_voice.model.transcript import VoiceTranscriptWriter
from sqlalchemy import create_engine


def test_record_turn_does_not_raise_on_db_error() -> None:
    # A SQLite engine with NO ``messages`` table → the insert raises "no such
    # table", which the writer must swallow (best-effort, like the episodic write).
    engine = create_engine("sqlite://")
    writer = VoiceTranscriptWriter(engine=engine, conversation_id="c1")
    writer.record_turn(
        user_text="what are my rights?",
        heard_text="you have strong rights.",
        truncated=False,
        now=datetime(2026, 6, 25, 12, 0, 0, tzinfo=UTC),
    )  # must not raise

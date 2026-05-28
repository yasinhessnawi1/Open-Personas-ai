"""Unit tests for persona_runtime.logging (T06; D-05-9, D-05-10)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from persona_runtime.logging import (
    JSONLTurnLogWriter,
    MemoryTurnLogWriter,
    TurnLog,
    TurnLogWriter,
    estimate_cost_cents,
)

if TYPE_CHECKING:
    from pathlib import Path


def _log(**overrides: object) -> TurnLog:
    base: dict[str, object] = {
        "conversation_id": "c1",
        "turn_index": 0,
        "tier_used": "frontier",
        "model_name": "claude-sonnet-4-6",
        "provider": "anthropic",
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "latency_ms": 123.4,
        "cost_cents": 0.105,
        "tool_calls": 0,
        "skill_used": None,
        "history_compacted": False,
        "timestamp": datetime.now(UTC),
    }
    base.update(overrides)
    return TurnLog(**base)  # type: ignore[arg-type]


class TestTurnLog:
    def test_constructs_with_all_fields(self) -> None:
        log = _log(tool_calls=2, skill_used="web_research", history_compacted=True)
        assert log.tool_calls == 2
        assert log.skill_used == "web_research"
        assert log.history_compacted is True

    def test_naive_timestamp_rejected(self) -> None:
        with pytest.raises(ValueError, match="naive datetime"):
            _log(timestamp=datetime(2026, 5, 28, 9, 0, 0))  # noqa: DTZ001 — intentionally naive

    def test_frozen(self) -> None:
        log = _log()
        with pytest.raises(ValueError, match="frozen|Instance is frozen"):
            log.tier_used = "mid"  # type: ignore[misc]

    def test_extra_field_forbidden(self) -> None:
        with pytest.raises(ValueError, match="Extra inputs|extra"):
            _log(bogus=True)

    def test_round_trips_via_json(self) -> None:
        log = _log(skill_used="document_drafting")
        restored = TurnLog.model_validate_json(log.model_dump_json())
        assert restored == log


class TestTurnLogWriterProtocol:
    def test_memory_writer_satisfies_protocol(self) -> None:
        assert isinstance(MemoryTurnLogWriter(), TurnLogWriter)

    def test_jsonl_writer_satisfies_protocol(self, tmp_path: Path) -> None:
        assert isinstance(JSONLTurnLogWriter(tmp_path), TurnLogWriter)


class TestMemoryTurnLogWriter:
    def test_accumulates_in_order(self) -> None:
        writer = MemoryTurnLogWriter()
        writer.write(_log(turn_index=0))
        writer.write(_log(turn_index=1))
        assert [log.turn_index for log in writer.logs] == [0, 1]


class TestJSONLTurnLogWriter:
    def test_appends_one_line_per_turn(self, tmp_path: Path) -> None:
        writer = JSONLTurnLogWriter(tmp_path / "turnlogs")
        writer.write(_log(conversation_id="conv", turn_index=0))
        writer.write(_log(conversation_id="conv", turn_index=1))

        path = tmp_path / "turnlogs" / "conv.jsonl"
        lines = path.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2
        parsed = [json.loads(line) for line in lines]
        assert [p["turn_index"] for p in parsed] == [0, 1]
        assert parsed[0]["provider"] == "anthropic"

    def test_separate_files_per_conversation(self, tmp_path: Path) -> None:
        writer = JSONLTurnLogWriter(tmp_path / "tl")
        writer.write(_log(conversation_id="a"))
        writer.write(_log(conversation_id="b"))
        assert (tmp_path / "tl" / "a.jsonl").exists()
        assert (tmp_path / "tl" / "b.jsonl").exists()


class TestCostEstimation:
    def test_known_pair_computes_from_table(self) -> None:
        # anthropic/claude-sonnet-4-6 = (0.30, 1.50) cents per 1k tokens.
        cost = estimate_cost_cents("anthropic", "claude-sonnet-4-6", 1000, 500)
        assert cost == pytest.approx(0.30 * 1.0 + 1.50 * 0.5)  # 0.30 + 0.75 = 1.05

    def test_zero_tokens_zero_cost(self) -> None:
        assert estimate_cost_cents("anthropic", "claude-sonnet-4-6", 0, 0) == 0.0

    def test_unknown_pair_returns_zero(self) -> None:
        assert estimate_cost_cents("acme", "mystery-model-v9", 1000, 1000) == 0.0

    def test_unknown_pair_called_twice_is_stable(self) -> None:
        # Two calls with the same unknown pair both cost 0.0; the once-only
        # warning guard (an internal set) must not change the return value.
        c1 = estimate_cost_cents("zzz", "once-only-model", 500, 500)
        c2 = estimate_cost_cents("zzz", "once-only-model", 500, 500)
        assert c1 == 0.0
        assert c2 == 0.0

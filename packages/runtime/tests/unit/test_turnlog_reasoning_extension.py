"""Unit tests for the Spec 20 T12 TurnLog reasoning extension (D-20-5).

Verifies the additive content-hash-only reasoning fields:

* ``reasoning_total_tokens`` and ``reasoning_text_hash`` default to ``None``
  so pre-Spec-20 callers stay green.
* Raw reasoning text NEVER appears in ``TurnLog.model_dump_json`` output
  (content-hash-only persistence per the D-15-X-hard-line-filter precedent).
* Negative ``reasoning_total_tokens`` is rejected (Field ge=0).
* JSON round-trip preserves the new fields.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

import pytest
from persona_runtime.logging import TurnLog
from pydantic import ValidationError


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, 0, tzinfo=UTC)


def _baseline_log_kwargs() -> dict[str, object]:
    return {
        "conversation_id": "c1",
        "turn_index": 0,
        "tier_used": "frontier",
        "model_name": "nvidia/llama-3.3-nemotron-super-49b-v1.5",
        "provider": "nvidia",
        "prompt_tokens": 80,
        "completion_tokens": 40,
        "latency_ms": 1500.0,
        "cost_cents": 0.7,
        "timestamp": _now(),
    }


class TestReasoningFieldsDefault:
    def test_default_to_none(self) -> None:
        log = TurnLog(**_baseline_log_kwargs())  # type: ignore[arg-type]
        assert log.reasoning_total_tokens is None
        assert log.reasoning_text_hash is None


class TestReasoningFieldsPopulated:
    def test_construction_records_hash_and_tokens(self) -> None:
        raw = "step 1: think\nstep 2: answer"
        expected_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        log = TurnLog(
            **_baseline_log_kwargs(),  # type: ignore[arg-type]
            reasoning_total_tokens=128,
            reasoning_text_hash=expected_hash,
        )
        assert log.reasoning_total_tokens == 128
        assert log.reasoning_text_hash == expected_hash


class TestReasoningFieldsValidation:
    def test_negative_token_count_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TurnLog(
                **_baseline_log_kwargs(),  # type: ignore[arg-type]
                reasoning_total_tokens=-1,
            )

    def test_extra_field_still_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TurnLog(
                **_baseline_log_kwargs(),  # type: ignore[arg-type]
                reasoning_undeclared="rogue",  # type: ignore[call-arg]
            )


class TestNoRawTextLeak:
    """D-20-5: raw reasoning text MUST NEVER appear in TurnLog serialisation."""

    def test_dump_json_excludes_raw_reasoning_text(self) -> None:
        raw = "SECRET reasoning content do not log"
        log = TurnLog(
            **_baseline_log_kwargs(),  # type: ignore[arg-type]
            reasoning_total_tokens=10,
            reasoning_text_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )
        payload = log.model_dump_json()
        assert "SECRET" not in payload
        assert "do not log" not in payload
        # The hash IS present (telemetry value).
        assert log.reasoning_text_hash is not None
        assert log.reasoning_text_hash in payload

    def test_round_trip_preserves_fields(self) -> None:
        raw = "hello-world-thinking"
        original = TurnLog(
            **_baseline_log_kwargs(),  # type: ignore[arg-type]
            reasoning_total_tokens=42,
            reasoning_text_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        )
        round_tripped = TurnLog.model_validate_json(original.model_dump_json())
        assert round_tripped.reasoning_total_tokens == 42
        assert round_tripped.reasoning_text_hash == original.reasoning_text_hash

    def test_model_dump_field_names(self) -> None:
        """The schema must expose the two new field names — no surprise renames."""
        log = TurnLog(**_baseline_log_kwargs())  # type: ignore[arg-type]
        as_dict = json.loads(log.model_dump_json())
        assert "reasoning_total_tokens" in as_dict
        assert "reasoning_text_hash" in as_dict

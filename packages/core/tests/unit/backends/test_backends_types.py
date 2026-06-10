"""Tests for ``persona.backends.types`` — response, stream, and tool shapes."""

from __future__ import annotations

from typing import Any

import pytest
from persona.backends.types import (
    ChatResponse,
    ReasoningBlock,
    StreamChunk,
    TokenUsage,
    ToolCallDelta,
    ToolSpec,
    reasoning_as_text,
    tool_spec_from_tool,
)
from persona.schema.tools import ToolCall, ToolResult
from pydantic import ValidationError


class TestTokenUsage:
    def test_construct_and_serialise_roundtrip(self) -> None:
        u = TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        round_tripped = TokenUsage.model_validate(u.model_dump())
        assert round_tripped == u

    def test_total_must_equal_sum(self) -> None:
        with pytest.raises(ValidationError, match="does not equal"):
            TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=99)

    def test_zero_counts_allowed(self) -> None:
        u = TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0)
        assert u.total_tokens == 0

    def test_negative_counts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TokenUsage(prompt_tokens=-1, completion_tokens=0, total_tokens=-1)

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TokenUsage.model_validate(
                {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                    "extra": "nope",
                }
            )

    def test_frozen(self) -> None:
        u = TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        with pytest.raises(ValidationError):
            u.prompt_tokens = 99  # type: ignore[misc]


class TestToolSpec:
    def test_construct(self) -> None:
        spec = ToolSpec(
            name="web_search",
            description="Search the web.",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}},
        )
        assert spec.name == "web_search"
        assert spec.parameters["type"] == "object"

    def test_parameters_kept_as_dict(self) -> None:
        # JSON Schema correctness is the provider's problem; we just carry the dict.
        spec = ToolSpec(name="x", description="y", parameters={"anything": True})
        assert spec.parameters == {"anything": True}

    def test_frozen_and_extra_forbid(self) -> None:
        with pytest.raises(ValidationError):
            ToolSpec.model_validate(
                {
                    "name": "x",
                    "description": "y",
                    "parameters": {},
                    "version": "v1",
                }
            )


class TestToolCallDelta:
    def test_minimum_construction(self) -> None:
        d = ToolCallDelta(call_id="abc")
        assert d.call_id == "abc"
        assert d.name_delta == ""
        assert d.arguments_delta == ""

    def test_with_args_delta(self) -> None:
        d = ToolCallDelta(call_id="abc", name_delta="web_", arguments_delta='{"qu')
        assert d.arguments_delta == '{"qu'


class TestChatResponse:
    def _usage(self) -> TokenUsage:
        return TokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    def test_construct_minimal(self) -> None:
        resp = ChatResponse(
            content="hi",
            usage=self._usage(),
            model="claude-sonnet-4-6",
            provider="anthropic",
            latency_ms=12.5,
        )
        assert resp.content == "hi"
        assert resp.tool_calls == []
        assert resp.latency_ms == 12.5

    def test_construct_with_tool_calls(self) -> None:
        tc = ToolCall(name="web_search", args={"query": "x"}, call_id="t1")
        resp = ChatResponse(
            content="",
            tool_calls=[tc],
            usage=self._usage(),
            model="gpt-4o",
            provider="openai",
            latency_ms=80.0,
        )
        assert resp.tool_calls == [tc]
        assert resp.content == ""

    def test_serialise_roundtrip(self) -> None:
        resp = ChatResponse(
            content="hello",
            usage=self._usage(),
            model="x",
            provider="y",
            latency_ms=0.0,
        )
        dumped = resp.model_dump()
        round_tripped = ChatResponse.model_validate(dumped)
        assert round_tripped == resp

    def test_negative_latency_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChatResponse(
                content="",
                usage=self._usage(),
                model="x",
                provider="y",
                latency_ms=-1.0,
            )

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ChatResponse.model_validate(
                {
                    "content": "",
                    "usage": self._usage().model_dump(),
                    "model": "x",
                    "provider": "y",
                    "latency_ms": 0.0,
                    "stop_reason": "end_turn",
                }
            )


class TestStreamChunk:
    def test_simple_delta(self) -> None:
        c = StreamChunk(delta="hello")
        assert c.delta == "hello"
        assert c.is_final is False
        assert c.usage is None
        assert c.tool_call_delta is None

    def test_final_with_usage(self) -> None:
        u = TokenUsage(prompt_tokens=1, completion_tokens=1, total_tokens=2)
        c = StreamChunk(delta="", is_final=True, usage=u)
        assert c.is_final is True
        assert c.usage == u

    def test_with_tool_call_delta(self) -> None:
        tcd = ToolCallDelta(call_id="abc", arguments_delta='{"x')
        c = StreamChunk(delta="", tool_call_delta=tcd)
        assert c.tool_call_delta == tcd

    def test_empty_delta_allowed(self) -> None:
        c = StreamChunk(delta="")
        assert c.delta == ""

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StreamChunk.model_validate({"delta": "x", "weird": True})


class TestToolSpecFromTool:
    def test_converts_tool_to_spec(self) -> None:
        class FakeTool:
            name: str = "web_search"
            description: str = "Search."
            parameters_schema: dict[str, Any] = {"type": "object"}

            def __call__(self, **kwargs: Any) -> ToolResult:  # noqa: ANN401, ARG002 — Tool Protocol shape
                return ToolResult(tool_name=self.name, content="ok")

        spec = tool_spec_from_tool(FakeTool())
        assert spec.name == "web_search"
        assert spec.description == "Search."
        assert spec.parameters == {"type": "object"}

    def test_copies_parameters_dict(self) -> None:
        # Mutating the source dict after conversion must not affect the spec.
        class FakeTool:
            name = "x"
            description = "y"
            parameters_schema: dict[str, Any] = {"a": 1}

            def __call__(self, **kwargs: Any) -> ToolResult:  # noqa: ANN401, ARG002 — Tool Protocol shape
                return ToolResult(tool_name=self.name, content="")

        source = FakeTool()
        spec = tool_spec_from_tool(source)
        source.parameters_schema["a"] = 999
        assert spec.parameters == {"a": 1}


# -----------------------------------------------------------------------------
# Spec 20 T12 — Reasoning surface (D-20-2)
# -----------------------------------------------------------------------------


class TestReasoningBlock:
    def test_construct_thinking_block(self) -> None:
        b = ReasoningBlock(kind="thinking", text="step 1", signature="sig-abc", index=0)
        assert b.kind == "thinking"
        assert b.text == "step 1"
        assert b.signature == "sig-abc"
        assert b.index == 0
        assert b.data is None
        assert b.id is None

    def test_construct_redacted_block(self) -> None:
        b = ReasoningBlock(kind="redacted_thinking", data="opaque-blob")
        assert b.kind == "redacted_thinking"
        assert b.text is None
        assert b.data == "opaque-blob"

    def test_frozen(self) -> None:
        b = ReasoningBlock(kind="thinking", text="x")
        with pytest.raises(ValidationError):
            b.text = "y"  # type: ignore[misc]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ReasoningBlock.model_validate({"kind": "thinking", "text": "x", "extra": "nope"})

    def test_kind_literal_enforced(self) -> None:
        with pytest.raises(ValidationError):
            ReasoningBlock(kind="bogus")  # type: ignore[arg-type]


class TestReasoningAsText:
    def test_none_returns_none(self) -> None:
        assert reasoning_as_text(None) is None

    def test_str_returns_str(self) -> None:
        assert reasoning_as_text("foo") == "foo"

    def test_concatenates_block_text(self) -> None:
        blocks = [
            ReasoningBlock(kind="thinking", text="a"),
            ReasoningBlock(kind="thinking", text="b"),
        ]
        assert reasoning_as_text(blocks) == "ab"

    def test_skips_blocks_without_text(self) -> None:
        blocks = [
            ReasoningBlock(kind="thinking", text="a"),
            ReasoningBlock(kind="redacted_thinking", data="opaque"),
            ReasoningBlock(kind="thinking", text="b"),
        ]
        assert reasoning_as_text(blocks) == "ab"

    def test_all_redacted_collapses_to_none(self) -> None:
        blocks = [ReasoningBlock(kind="redacted_thinking", data="opaque")]
        assert reasoning_as_text(blocks) is None

    def test_empty_list_collapses_to_none(self) -> None:
        assert reasoning_as_text([]) is None


class TestStreamChunkReasoning:
    def test_default_reasoning_is_none(self) -> None:
        c = StreamChunk(delta="hi")
        assert c.reasoning is None

    def test_str_arm_accepted(self) -> None:
        c = StreamChunk(delta="hi", reasoning="thinking step")
        assert c.reasoning == "thinking step"

    def test_list_arm_accepted(self) -> None:
        blocks = [ReasoningBlock(kind="thinking", text="a", signature="sig-1")]
        c = StreamChunk(delta="hi", reasoning=blocks)
        assert isinstance(c.reasoning, list)
        assert c.reasoning[0].signature == "sig-1"

    def test_invalid_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StreamChunk(delta="hi", reasoning=123)  # type: ignore[arg-type]

    def test_extra_fields_rejected(self) -> None:
        with pytest.raises(ValidationError):
            StreamChunk.model_validate({"delta": "hi", "extra": "nope"})

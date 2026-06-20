"""stream_chat SSE bridge — events flush in true emission order, live.

The loop fires ``on_event`` from inside ``loop.turn`` (between/around chunk
yields). A tool-heavy round emits NO text chunks, so the events must still reach
the client interleaved in emission order rather than batched at the next chunk.
``stream_chat`` bridges the callback into the generator via a queue; these unit
tests pin the resulting frame ordering without needing Postgres.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest
from persona.schema.conversation import Conversation, ConversationMessage
from persona.schema.tools import ToolCall, ToolResult
from persona_api.services import chat_service
from persona_runtime.agentic.events import RunEvent

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable

    from persona.backends import StreamChunk


class _ToolEventLoop:
    """Scripted loop that emits tier + a tool round BEFORE any text chunk.

    Mirrors a real tool-using turn: the model decides a tier, calls a tool, the
    loop surfaces tool_calling then tool_result, and only then streams the answer.
    With the pre-bridge buffering these events were stuck until the first chunk;
    the queue bridge must surface them in order regardless.
    """

    async def turn(
        self,
        conversation: Conversation,
        user_message: str,  # noqa: ARG002 — real-loop signature compat
        on_event: Callable[[RunEvent], Awaitable[None]] | None = None,
        *,
        turn_has_image: bool = False,  # noqa: ARG002 — real-loop kwarg compat
        images: list[object] | None = None,  # noqa: ARG002
        documents: list[object] | None = None,  # noqa: ARG002
        document_context: object = None,  # noqa: ARG002
    ) -> AsyncIterator[StreamChunk]:
        from persona.backends import (
            StreamChunk,  # noqa: PLC0415 — local keeps TYPE_CHECKING import light
        )

        assert on_event is not None
        await on_event(RunEvent.tier("mid"))
        call = ToolCall(name="code_execution", args={"code": "pdf.savefig(fig)"}, call_id="c1")
        await on_event(RunEvent.tool_calling(-1, [call]))
        result = ToolResult(tool_name="code_execution", content="ok", call_id="c1")
        await on_event(RunEvent.tool_result(-1, "code_execution", result))
        now = datetime.now(UTC)
        conversation.messages.append(
            ConversationMessage(role="assistant", content="done", created_at=now)
        )
        yield StreamChunk(delta="done", is_final=False)
        yield StreamChunk(delta="", is_final=True)


class _NoopCredits:
    def deduct(self, **_kwargs: object) -> None: ...


class _FakeConn:
    def __enter__(self) -> _FakeConn:
        return self

    def __exit__(self, *_a: object) -> None: ...


class _FakeEngine:
    def begin(self) -> _FakeConn:
        return _FakeConn()


def _parse_sse(frames: list[bytes]) -> list[tuple[str, str]]:
    """Split SSE byte frames into ``(event, data)`` pairs."""
    import json

    out: list[tuple[str, str]] = []
    for frame in frames:
        text = frame.decode()
        event = ""
        data = ""
        for line in text.splitlines():
            if line.startswith("event: "):
                event = line.removeprefix("event: ")
            elif line.startswith("data: "):
                data = line.removeprefix("data: ")
        if event:
            # Validate the data is JSON so a malformed frame fails loudly here.
            json.loads(data) if data else None
            out.append((event, data))
    return out


@pytest.mark.asyncio
async def test_tool_events_stream_in_order_before_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """tool_calling → tool_result → chunk → done, with tier folded into done."""
    import json

    monkeypatch.setattr(
        chat_service,
        "_load_conversation",
        lambda _conn, _cid: Conversation(conversation_id="c1", persona_id="astrid", messages=[]),
    )
    monkeypatch.setattr(chat_service, "_persist_turn", lambda **_kwargs: None)

    async def _build_loop(_pid: str) -> _ToolEventLoop:
        return _ToolEventLoop()

    frames = [
        frame
        async for frame in chat_service.stream_chat(
            rls_engine=_FakeEngine(),  # type: ignore[arg-type]
            loop_builder=_build_loop,  # type: ignore[arg-type]
            owner_id="user_1",
            conversation_id="c1",
            user_message="generate a pdf",
            channel=None,
            credits_policy=_NoopCredits(),  # type: ignore[arg-type]
        )
    ]
    events = _parse_sse(frames)
    kinds = [e for e, _ in events]

    # The tool round surfaces BEFORE the terminal done, in emission order.
    assert "tool_calling" in kinds
    assert "tool_result" in kinds
    assert kinds.index("tool_calling") < kinds.index("tool_result") < kinds.index("done")

    # `tier` rides the done event — it is NOT emitted as its own SSE frame.
    assert "tier" not in kinds
    done = next(json.loads(d) for e, d in events if e == "done")
    assert done["tier"] == "mid"


@pytest.mark.asyncio
async def test_loop_error_propagates_and_skips_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loop that raises mid-turn surfaces the error — no done, no persist."""

    class _RaisingLoop:
        async def turn(
            self,
            conversation: Conversation,  # noqa: ARG002
            user_message: str,  # noqa: ARG002
            on_event: Callable[[RunEvent], Awaitable[None]] | None = None,
            **_kwargs: object,
        ) -> AsyncIterator[StreamChunk]:
            assert on_event is not None
            await on_event(RunEvent.tool_calling(-1, [ToolCall(name="x", args={}, call_id="c1")]))
            raise RuntimeError("loop blew up")
            yield  # pragma: no cover — unreachable, makes this an async generator

    persisted: list[object] = []
    monkeypatch.setattr(
        chat_service,
        "_load_conversation",
        lambda _conn, _cid: Conversation(conversation_id="c1", persona_id="astrid", messages=[]),
    )
    monkeypatch.setattr(chat_service, "_persist_turn", lambda **_kwargs: persisted.append(object()))

    async def _build_loop(_pid: str) -> _RaisingLoop:
        return _RaisingLoop()

    collected: list[bytes] = []

    async def _consume() -> None:
        async for frame in chat_service.stream_chat(
            rls_engine=_FakeEngine(),  # type: ignore[arg-type]
            loop_builder=_build_loop,  # type: ignore[arg-type]
            owner_id="user_1",
            conversation_id="c1",
            user_message="go",
            channel=None,
            credits_policy=_NoopCredits(),  # type: ignore[arg-type]
        ):
            collected.append(frame)

    with pytest.raises(RuntimeError, match="loop blew up"):
        await _consume()

    # The tool_calling frame that fired before the raise still reached the client…
    assert any(b"tool_calling" in f for f in collected)
    # …but no done frame, and the turn was NOT persisted (D-08-6).
    assert not any(b"event: done" in f for f in collected)
    assert persisted == []

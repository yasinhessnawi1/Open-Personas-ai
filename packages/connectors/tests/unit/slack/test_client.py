"""SlackClient — the Web API boundary (Spec C3), with an httpx MockTransport.

Asserts: the bot token rides in the ``Authorization: Bearer`` header (and NEVER leaks on a
transport fault); the ``{"ok": false}`` envelope → a domain error; a 429 → a rate-limit
domain error with ``Retry-After``; ``conversations.open`` extracts the ``im`` channel id.
"""

from __future__ import annotations

# ruff: noqa: ARG001 — httpx MockTransport handlers must take `request`; many ignore it.
from typing import TYPE_CHECKING

import httpx
import pytest
from persona_connectors.errors import SlackApiError, SlackRateLimitError
from persona_connectors.slack.client import SlackClient
from pydantic import SecretStr

if TYPE_CHECKING:
    from collections.abc import Callable

_TOKEN = "xoxb-super-secret.value"  # noqa: S105 — test fixture, not a real secret


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> SlackClient:
    return SlackClient(
        bot_token=SecretStr(_TOKEN),
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
        api_base_url="https://slack.test/api",
    )


@pytest.mark.asyncio
async def test_auth_test_returns_ids() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/auth.test"
        return httpx.Response(200, json={"ok": True, "user_id": "U_BOT", "team_id": "T1"})

    body = await _client(handler).auth_test()
    assert body["user_id"] == "U_BOT"


@pytest.mark.asyncio
async def test_auth_header_carries_bearer_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"ok": True})

    await _client(handler).auth_test()
    assert seen["auth"] == f"Bearer {_TOKEN}"


@pytest.mark.asyncio
async def test_conversations_open_returns_the_im_channel_id() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "channel": {"id": "D123"}})

    assert await _client(handler).conversations_open(user_id="U456") == "D123"


@pytest.mark.asyncio
async def test_conversations_open_missing_channel_is_an_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})  # no channel

    with pytest.raises(SlackApiError):
        await _client(handler).conversations_open(user_id="U456")


@pytest.mark.asyncio
async def test_post_message_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/chat.postMessage"
        return httpx.Response(200, json={"ok": True, "ts": "1700000000.000100"})

    body = await _client(handler).chat_post_message(channel="D123", text="hi")
    assert body["ts"] == "1700000000.000100"


@pytest.mark.asyncio
async def test_ok_false_maps_to_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": False, "error": "channel_not_found"})

    with pytest.raises(SlackApiError) as exc:
        await _client(handler).chat_post_message(channel="Dx", text="hi")
    assert exc.value.context["error"] == "channel_not_found"


@pytest.mark.asyncio
async def test_429_carries_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "3"})

    with pytest.raises(SlackRateLimitError) as exc:
        await _client(handler).chat_post_message(channel="D123", text="hi")
    assert exc.value.retry_after == 3


@pytest.mark.asyncio
async def test_token_never_leaks_on_a_transport_fault() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(SlackApiError) as exc:
        await _client(handler).auth_test()
    assert _TOKEN not in str(exc.value)
    assert all(_TOKEN not in v for v in exc.value.context.values())
    assert exc.value.__cause__ is None  # suppressed with `from None`

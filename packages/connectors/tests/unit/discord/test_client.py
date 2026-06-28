"""DiscordClient — the REST boundary (Spec C3), with an httpx MockTransport.

Asserts the research-flagged facts: the bot token rides in the ``Authorization: Bot``
header (and NEVER leaks on a transport fault); a 429 / code 40003 → a rate-limit
domain error with ``retry_after``; codes 50007/50278 (the DM-ability gate) → a
cannot-deliver error; any other rejection → a generic API error.
"""

from __future__ import annotations

# ruff: noqa: ARG001 — httpx MockTransport handlers must take `request`; many ignore it.
from typing import TYPE_CHECKING

import httpx
import pytest
from persona_connectors.discord.client import DiscordClient
from persona_connectors.errors import (
    DiscordApiError,
    DiscordCannotDeliverError,
    DiscordRateLimitError,
)
from pydantic import SecretStr

if TYPE_CHECKING:
    from collections.abc import Callable

_TOKEN = "super-secret-bot-token.value.xyz"  # noqa: S105 — a test fixture, not a real secret


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> DiscordClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return DiscordClient(
        bot_token=SecretStr(_TOKEN), http=http, api_base_url="https://discord.test/api/v10"
    )


# --- happy paths ---


@pytest.mark.asyncio
async def test_get_current_user_returns_the_bot_user() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v10/users/@me"
        return httpx.Response(200, json={"id": "bot1", "username": "PersonaBot"})

    user = await _client(handler).get_current_user()
    assert user["id"] == "bot1"


@pytest.mark.asyncio
async def test_auth_header_carries_the_bot_token() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"id": "bot1"})

    await _client(handler).get_current_user()
    assert seen["auth"] == f"Bot {_TOKEN}"


@pytest.mark.asyncio
async def test_create_dm_then_send_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/users/@me/channels":
            return httpx.Response(200, json={"id": "dm-9", "type": 1})
        return httpx.Response(200, json={"id": "msg-1"})

    client = _client(handler)
    dm = await client.create_dm(recipient_id="user-7")
    assert dm["id"] == "dm-9"
    msg = await client.send_message(channel_id="dm-9", content="hello")
    assert msg["id"] == "msg-1"


@pytest.mark.asyncio
async def test_trigger_typing_204_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v10/channels/dm-9/typing"
        return httpx.Response(204)

    assert await _client(handler).trigger_typing(channel_id="dm-9") is None


# --- the DM-ability gate (50007 / 50278) → cannot-deliver ---


@pytest.mark.asyncio
@pytest.mark.parametrize("code", [50007, 50278])
async def test_cannot_dm_maps_to_cannot_deliver(code: int) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"code": code, "message": "Cannot send messages"})

    with pytest.raises(DiscordCannotDeliverError) as exc:
        await _client(handler).send_message(channel_id="dm-9", content="hi")
    assert exc.value.context["code"] == str(code)


# --- rate limits ---


@pytest.mark.asyncio
async def test_429_carries_float_retry_after() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"message": "rate limited", "retry_after": 1.5})

    with pytest.raises(DiscordRateLimitError) as exc:
        await _client(handler).send_message(channel_id="dm-9", content="hi")
    assert exc.value.retry_after == 1.5
    assert isinstance(exc.value.retry_after, float)


@pytest.mark.asyncio
async def test_opening_dms_too_fast_40003_is_a_rate_limit() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 40003, "message": "opening DMs too fast"})

    with pytest.raises(DiscordRateLimitError):
        await _client(handler).create_dm(recipient_id="user-7")


# --- generic + shape + credential safety ---


@pytest.mark.asyncio
async def test_other_rejection_maps_to_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"code": 50035, "message": "Invalid Form Body"})

    with pytest.raises(DiscordApiError) as exc:
        await _client(handler).send_message(channel_id="dm-9", content="hi")
    assert not isinstance(exc.value, (DiscordRateLimitError, DiscordCannotDeliverError))


@pytest.mark.asyncio
async def test_unexpected_shape_raises_api_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    with pytest.raises(DiscordApiError):
        await _client(handler).get_current_user()


@pytest.mark.asyncio
async def test_token_never_leaks_on_a_transport_fault() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(DiscordApiError) as exc:
        await _client(handler).get_current_user()
    # The token must not surface in the message, the context, or a chained cause.
    assert _TOKEN not in str(exc.value)
    assert all(_TOKEN not in v for v in exc.value.context.values())
    assert exc.value.__cause__ is None  # suppressed with `from None`

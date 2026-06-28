"""The Discord REST client (Spec C3) — the thin transport boundary.

The Discord REST API is plain JSON-over-HTTPS (``{base}/v10/<path>`` with
``Authorization: Bot <token>``, JSON replies; a non-2xx carries a JSON
``{"code", "message"}``). So this adapter talks to it with ``httpx`` directly rather
than a heavyweight SDK that would invert control and duplicate C1's flow
(D-C3-X-no-new-dep). The client is the **single Discord REST I/O boundary**: every
call the DM adapter needs (``GET /users/@me`` / ``POST /users/@me/channels`` /
``POST /channels/{id}/messages`` / ``POST /channels/{id}/typing``) goes through one
``_request`` that maps every transport fault or logical rejection to a domain error:

- a **429** or code **40003** → :class:`~persona_connectors.errors.DiscordRateLimitError`
  (``retry_after``, retryable → ``pending``);
- codes **50007 / 50278** (the DM-ability gate) →
  :class:`~persona_connectors.errors.DiscordCannotDeliverError` (→ ``failed``, durable);
- anything else → :class:`~persona_connectors.errors.DiscordApiError`.

**Credential safety (D-C3-3).** The bot token rides in the ``Authorization: Bot``
**header** (never the URL — safer than Telegram). It is unwrapped from its
:class:`~pydantic.SecretStr` only at the call site and **never** appears in a log
line / exception message / ``context``: on an ``httpx`` failure the underlying
exception is suppressed with ``raise … from None`` and the domain error carries only
the method + path + status / Discord ``code``.

This module is **api-free** (httpx + persona-core errors only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from persona_connectors.errors import (
    DiscordApiError,
    DiscordCannotDeliverError,
    DiscordRateLimitError,
)

if TYPE_CHECKING:
    from pydantic import SecretStr

__all__ = ["DISCORD_MAX_MESSAGE_CHARS", "DiscordClient"]

# Discord caps a (non-Nitro bot) message at 2000 characters, counted in Unicode
# code points (C3-R-1); the shared splitter budgets against this. Exposed here as
# the single source of the platform fact.
DISCORD_MAX_MESSAGE_CHARS = 2000

# Discord JSON error codes the client maps specially (C3-R-1).
_CANNOT_DELIVER_CODES = frozenset({50007, 50278})
_OPENING_DMS_TOO_FAST = 40003
# A conservative default backoff when Discord rate-limits without a numeric hint.
_DEFAULT_BACKOFF_SECONDS = 1.0


class DiscordClient:
    """A thin async client over the Discord REST API (Spec C3).

    Holds the bot token (a :class:`~pydantic.SecretStr`) and an injected
    :class:`httpx.AsyncClient` (DI — the composition root owns the client's
    timeouts/pool). No globals, no module state.
    """

    def __init__(
        self,
        *,
        bot_token: SecretStr,
        http: httpx.AsyncClient,
        api_base_url: str = "https://discord.com/api/v10",
    ) -> None:
        self._token = bot_token
        self._http = http
        self._base = api_base_url.rstrip("/")

    def _auth_header(self) -> dict[str, str]:
        """The auth header. Contains the token — NEVER log or surface this dict."""
        return {"Authorization": f"Bot {self._token.get_secret_value()}"}

    async def _request(
        self, method: str, path: str, *, json: dict[str, object] | None = None
    ) -> object:
        """Send one REST call and return its decoded body (or raise a domain error).

        Args:
            method: The HTTP method (``GET`` / ``POST``).
            path: The API path (e.g. ``/users/@me``), appended to the v10 base.
            json: The optional JSON request body.

        Returns:
            The decoded JSON body on success, or ``None`` for a ``204 No Content``.

        Raises:
            DiscordRateLimitError: A ``429`` or code ``40003`` — back off ``retry_after``.
            DiscordCannotDeliverError: Codes ``50007`` / ``50278`` — the DM-ability gate.
            DiscordApiError: Any other transport fault or logical rejection.
        """
        try:
            response = await self._http.request(
                method, f"{self._base}{path}", json=json, headers=self._auth_header()
            )
        except httpx.HTTPError:
            # Suppress the httpx exception entirely (``from None``) — defensive even
            # though the token is in the header, not the URL.
            raise DiscordApiError(
                "discord request failed", context={"method": method, "path": path}
            ) from None
        return self._parse(method, path, response)

    @staticmethod
    def _parse(method: str, path: str, response: httpx.Response) -> object:
        """Parse a Discord REST reply, mapping rejections to domain errors."""
        if response.status_code == 204:  # No Content (e.g. trigger typing)
            return None
        try:
            raw: object = response.json()
        except ValueError:
            raw = None
        if 200 <= response.status_code < 300:
            return raw

        code: object = None
        message = ""
        if isinstance(raw, dict):
            code = raw.get("code")
            message = str(raw.get("message", "")).strip()
        context = {
            "method": method,
            "path": path,
            "status": str(response.status_code),
            "code": str(code),
        }
        if response.status_code == 429:
            raise DiscordRateLimitError(
                message or "discord rate-limited",
                retry_after=DiscordClient._retry_after(raw, response),
                context=context,
            )
        if code == _OPENING_DMS_TOO_FAST:
            raise DiscordRateLimitError(
                "opening DMs too fast", retry_after=_DEFAULT_BACKOFF_SECONDS, context=context
            )
        if code in _CANNOT_DELIVER_CODES:
            raise DiscordCannotDeliverError(
                message or "cannot send a DM to this user", context=context
            )
        raise DiscordApiError(
            f"discord API error: {message}" if message else "discord API error", context=context
        )

    @staticmethod
    def _retry_after(raw: object, response: httpx.Response) -> float:
        """The 429 backoff (seconds) — the body ``retry_after`` else the header, else default."""
        if isinstance(raw, dict):
            value = raw.get("retry_after")
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return float(value)
        header = response.headers.get("Retry-After")
        if header is not None:
            try:
                return float(header)
            except ValueError:
                return _DEFAULT_BACKOFF_SECONDS
        return _DEFAULT_BACKOFF_SECONDS

    @staticmethod
    def _as_dict(result: object, path: str) -> dict[str, object]:
        """Assert ``result`` is a JSON object (a Discord User / Channel / Message)."""
        if not isinstance(result, dict):
            raise DiscordApiError(
                "discord returned an unexpected result shape", context={"path": path}
            )
        return result

    async def get_current_user(self) -> dict[str, object]:
        """Return the bot's own ``User`` (``GET /users/@me``) — validates the token + id.

        Resolves the bot's user id at startup so the inbound classifier can ignore the
        bot's own ``MESSAGE_CREATE`` echoes (loop prevention, D-C3-5).
        """
        return self._as_dict(await self._request("GET", "/users/@me"), "/users/@me")

    async def create_dm(self, *, recipient_id: str) -> dict[str, object]:
        """Open (or fetch) a DM channel with a user (``POST /users/@me/channels``).

        Returns the DM channel object (``type == 1``; ``id`` is the channel to send
        to). The DM-ability gate (``50278`` / ``50007``) can surface on this call or
        the subsequent message send — both raise
        :class:`~persona_connectors.errors.DiscordCannotDeliverError` (C3-R-1).
        """
        return self._as_dict(
            await self._request("POST", "/users/@me/channels", json={"recipient_id": recipient_id}),
            "/users/@me/channels",
        )

    async def send_message(self, *, channel_id: str, content: str) -> dict[str, object]:
        """Send a message to a channel (``POST /channels/{id}/messages``) → the ``Message``."""
        path = f"/channels/{channel_id}/messages"
        return self._as_dict(await self._request("POST", path, json={"content": content}), path)

    async def trigger_typing(self, *, channel_id: str) -> None:
        """Show the typing indicator (``POST /channels/{id}/typing``) — expires after 10 s."""
        await self._request("POST", f"/channels/{channel_id}/typing")

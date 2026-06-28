"""The Slack Web API client (Spec C3) — the thin transport boundary.

The Slack Web API is plain JSON-over-HTTPS (``POST {base}/<method>`` with
``Authorization: Bearer xoxb-…``, a JSON reply that **always** carries ``{"ok": bool,
…}`` — ``ok: false`` means a logical rejection with an ``error`` code). So this adapter
talks to it with ``httpx`` directly rather than a heavyweight SDK that would invert
control and duplicate C1's flow (D-C3-X-no-new-dep). The client is the **single Slack
Web-API I/O boundary**: every call the DM adapter needs (``auth.test`` /
``conversations.open`` / ``chat.postMessage``) goes through one ``_call`` that maps every
transport fault or ``ok: false`` rejection to a
:class:`~persona_connectors.errors.SlackApiError`, and a ``429`` to a
:class:`~persona_connectors.errors.SlackRateLimitError` carrying ``Retry-After``.

**Slack DMs are unconditional** (the app is installed in the workspace), so there is no
Discord-style cannot-deliver gate — a failed send is a transient/transport error, not a
relationship gate.

**Credential safety (D-C3-3).** The bot token rides in the ``Authorization: Bearer``
header (never the URL). It is unwrapped from its :class:`~pydantic.SecretStr` only at the
call site and **never** appears in a log line / exception message / ``context``: on an
``httpx`` failure the underlying exception is suppressed with ``raise … from None`` and
the domain error carries only the method + the Slack ``error`` code.

This module is **api-free** (httpx + persona-core errors only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

from persona_connectors.errors import SlackApiError, SlackRateLimitError

if TYPE_CHECKING:
    from pydantic import SecretStr

__all__ = ["SLACK_MAX_MESSAGE_CHARS", "SlackClient"]

# Slack's hard per-message ``text`` cap is 40000 characters (the render splits at a far
# smaller, readable budget — slack/render.py). Exposed here as the single platform fact.
SLACK_MAX_MESSAGE_CHARS = 40000

# A conservative default backoff when Slack rate-limits without a numeric Retry-After.
_DEFAULT_BACKOFF_SECONDS = 1


class SlackClient:
    """A thin async client over the Slack Web API (Spec C3).

    Holds the bot token (a :class:`~pydantic.SecretStr`) and an injected
    :class:`httpx.AsyncClient` (DI — the composition root owns the client's
    timeouts/pool). No globals, no module state.
    """

    def __init__(
        self,
        *,
        bot_token: SecretStr,
        http: httpx.AsyncClient,
        api_base_url: str = "https://slack.com/api",
    ) -> None:
        self._token = bot_token
        self._http = http
        self._base = api_base_url.rstrip("/")

    def _auth_header(self) -> dict[str, str]:
        """The auth header. Contains the token — NEVER log or surface this dict."""
        return {"Authorization": f"Bearer {self._token.get_secret_value()}"}

    async def _call(self, method: str, payload: dict[str, object]) -> dict[str, object]:
        """POST one Web API method and return its body (or raise a domain error).

        Args:
            method: The Web API method name (e.g. ``"chat.postMessage"``).
            payload: The JSON request body.

        Returns:
            The decoded ``ok: true`` reply body.

        Raises:
            SlackRateLimitError: Slack returned ``429`` — back off ``Retry-After``.
            SlackApiError: Any transport fault or ``ok: false`` rejection.
        """
        try:
            response = await self._http.post(
                f"{self._base}/{method}", json=payload, headers=self._auth_header()
            )
        except httpx.HTTPError:
            raise SlackApiError("slack request failed", context={"method": method}) from None
        return self._parse(method, response)

    @staticmethod
    def _parse(method: str, response: httpx.Response) -> dict[str, object]:
        """Parse a Web API reply, mapping 429 + ``ok: false`` to domain errors."""
        if response.status_code == 429:
            header = response.headers.get("Retry-After")
            retry_after = (
                int(header) if header is not None and header.isdigit() else _DEFAULT_BACKOFF_SECONDS
            )
            raise SlackRateLimitError(
                "slack rate-limited", retry_after=retry_after, context={"method": method}
            )
        try:
            raw: object = response.json()
        except ValueError:
            raw = None
        if not isinstance(raw, dict):
            raise SlackApiError(
                "slack returned a non-object response",
                context={"method": method, "status": str(response.status_code)},
            )
        if raw.get("ok") is True:
            return raw
        error = str(raw.get("error", "")).strip()
        raise SlackApiError(
            f"slack API error: {error}" if error else "slack API error",
            context={"method": method, "error": error},
        )

    async def auth_test(self) -> dict[str, object]:
        """Validate the token + read the bot's own ids (``auth.test``).

        Returns the reply with ``user_id`` (the bot's Slack user id — for ignoring its own
        message echoes, loop prevention) + ``team_id``.
        """
        return await self._call("auth.test", {})

    async def conversations_open(self, *, user_id: str) -> str:
        """Open (or fetch) a DM channel with a user (``conversations.open``) → the ``im`` id.

        Slack DMs are unconditional (the app is installed in the workspace), so this simply
        materialises the ``D…`` channel to post to.
        """
        body = await self._call("conversations.open", {"users": user_id})
        channel = body.get("channel")
        channel_id = channel.get("id") if isinstance(channel, dict) else None
        if not isinstance(channel_id, str) or not channel_id:
            raise SlackApiError(
                "slack conversations.open returned no channel id",
                context={"method": "conversations.open"},
            )
        return channel_id

    async def chat_post_message(self, *, channel: str, text: str) -> dict[str, object]:
        """Send a message to a channel (``chat.postMessage``) — mrkdwn by default."""
        return await self._call("chat.postMessage", {"channel": channel, "text": text})

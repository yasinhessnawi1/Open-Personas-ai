"""Discord OAuth account linking (Spec C3, D-C3-4) — the carrier, not the lifecycle.

C1 owns the linking *lifecycle* (issue → redeem → bind → resolve → unlink) and ALL its
security (C1-D-5): the token is ``secrets.token_urlsafe(32)`` (~256 bits, unguessable),
stored only as a sha256 hash, **single-use** (consumed atomically on redeem),
**short-TTL**, and **platform-bound** — every violation raises
:class:`~persona_connectors.errors.LinkTokenInvalidError` (fail-closed). C3 **reuses**
that unchanged — the first OAuth carrier proves C1's linking abstraction accommodates
OAuth, not just Telegram's deep link (C3-R-3); the abstraction is validated, not amended.

This module is only Discord's **OAuth carrier** around it (D-C3-4):

- :func:`build_authorize_url` — the ``https://discord.com/oauth2/authorize`` URL with
  **the C1 ``LinkToken`` carried as the OAuth ``state``** (unguessable / single-use /
  short-TTL / platform-bound = free CSRF protection). ``scope=identify bot`` so one
  consent both (a) yields a code we exchange → ``/users/@me`` for the user id (the
  binding) and (b) adds the bot to a shared guild, **establishing DM-ability** (§1).
- :class:`DiscordOAuthClient` — the OAuth I/O (``code`` → access token → ``/users/@me``
  → the user id). Distinct from the bot REST client: the exchange uses the app's
  ``client_id``/``client_secret`` (HTTP Basic), the identity fetch a user Bearer token.
- :class:`DiscordLinkingService` — the trigger-agnostic orchestration: ``issue`` an
  authorize URL, and **on the out-of-band OAuth callback** ``complete_oauth`` exchanges
  the code → identity and binds it via C1's ``redeem_and_bind`` (the **binding WRITE**;
  symmetric with Telegram's inline ``/start`` redeem — both call the SAME C1 bind, so
  the binding shape the shared ``resolver.resolve`` reads is identical by construction).

**The state integrity boundary (the CSRF-class defence):** a tampered / replayed /
expired / wrong-platform ``state`` never binds — C1's ``redeem_and_bind`` raises
:class:`~persona_connectors.errors.LinkTokenInvalidError` before any bind (fail-closed).

**api-free**: pure carrier logic + httpx + C1's owned-surface ``LinkingService``; no
``persona_api``. Credential safety (D-C3-3): the OAuth ``client_secret`` is a
``SecretStr``, used only in the HTTP-Basic tuple at the call site, never logged; httpx
faults are suppressed ``from None``.
"""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import httpx

from persona_connectors.discord.inbound import PLATFORM
from persona_connectors.errors import DiscordApiError

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from pydantic import SecretStr

    from persona_connectors.domain.linking import LinkingService

__all__ = [
    "DiscordLinkingService",
    "DiscordOAuthClient",
    "OAuthIdentityResolver",
    "build_authorize_url",
]

# The OAuth2 authorize endpoint (NOT under /api). The token + identity endpoints ride
# the configurable REST base (``DiscordOAuthClient``).
_AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
# ``identify`` resolves the user id (the binding); ``bot`` adds the bot to a shared
# guild in the same consent → establishes DM-ability (D-C3-4 / C3-R-1).
_OAUTH_SCOPES = "identify bot"


def build_authorize_url(
    *, client_id: str, redirect_uri: str, state: str, scopes: str = _OAUTH_SCOPES
) -> str:
    """Build the Discord OAuth2 authorize URL with the ``LinkToken`` as ``state`` (D-C3-4).

    The ``state`` IS the C1 link token — unguessable / single-use / short-TTL /
    platform-bound — so it doubles as the OAuth CSRF guard (no second mechanism needed).
    Spaces in ``scope`` are percent-encoded (``identify%20bot``).
    """
    params = {
        "response_type": "code",
        "client_id": client_id,
        "scope": scopes,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{_AUTHORIZE_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


@runtime_checkable
class OAuthIdentityResolver(Protocol):
    """Resolve an OAuth ``code`` to the authorizing user's Discord id (the carrier I/O port)."""

    async def resolve_user_id(self, code: str) -> str:
        """Exchange ``code`` → access token → ``/users/@me`` and return the user id."""
        ...


class DiscordOAuthClient:
    """The Discord OAuth I/O (``code`` → access token → user id) over ``httpx``.

    Holds the app credentials (``client_id`` + the ``SecretStr`` ``client_secret``) and
    the redirect URI; an injected :class:`httpx.AsyncClient` (DI). The secret is
    unwrapped only in the HTTP-Basic tuple at the call site and never logged / surfaced;
    httpx faults are suppressed ``from None`` (D-C3-3).
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: SecretStr,
        redirect_uri: str,
        http: httpx.AsyncClient,
        api_base_url: str = "https://discord.com/api/v10",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http
        self._base = api_base_url.rstrip("/")

    async def resolve_user_id(self, code: str) -> str:
        """Exchange ``code`` for an access token, then fetch the authorizing user's id."""
        access_token = await self._exchange_code(code)
        return await self._fetch_user_id(access_token)

    async def _exchange_code(self, code: str) -> str:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._redirect_uri,
        }
        try:
            response = await self._http.post(
                f"{self._base}/oauth2/token",
                data=data,
                auth=(self._client_id, self._client_secret.get_secret_value()),
            )
        except httpx.HTTPError:
            raise DiscordApiError(
                "discord oauth token exchange failed", context={"step": "exchange"}
            ) from None
        return self._json_field(response, "access_token", step="exchange")

    async def _fetch_user_id(self, access_token: str) -> str:
        try:
            response = await self._http.get(
                f"{self._base}/users/@me",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.HTTPError:
            raise DiscordApiError(
                "discord oauth identity fetch failed", context={"step": "identity"}
            ) from None
        return self._json_field(response, "id", step="identity")

    @staticmethod
    def _json_field(response: httpx.Response, field: str, *, step: str) -> str:
        """Extract a required string ``field`` from a 2xx JSON body, else a domain error."""
        if response.status_code != 200:
            raise DiscordApiError(
                f"discord oauth {step} rejected",
                context={"step": step, "status": str(response.status_code)},
            )
        try:
            body: object = response.json()
        except ValueError:
            body = None
        value = body.get(field) if isinstance(body, dict) else None
        if not isinstance(value, str) or not value:
            raise DiscordApiError(
                f"discord oauth {step} response missing {field}", context={"step": step}
            )
        return value


class DiscordLinkingService:
    """Discord's OAuth carrier around C1's :class:`LinkingService` (issue link / bind).

    Holds no state beyond its injected C1 ``LinkingService`` + the OAuth resolver + the
    app's ``client_id``/``redirect_uri``. The token generation, single-use consumption,
    TTL, platform-binding, and the bind all live in C1 — this only wraps them in
    Discord's OAuth carrier.
    """

    def __init__(
        self,
        *,
        linking: LinkingService,
        oauth: OAuthIdentityResolver,
        client_id: str,
        redirect_uri: str,
    ) -> None:
        self._linking = linking
        self._oauth = oauth
        self._client_id = client_id
        self._redirect_uri = redirect_uri

    def issue_authorize_url(self, *, owner_id: str, now: datetime, ttl: timedelta) -> str:
        """Issue a one-time link for ``owner_id`` and return the Discord authorize URL.

        Delegates token generation to C1 (single-use, short-TTL, unguessable,
        platform-bound), then carries the opaque token as the OAuth ``state``.
        """
        state = self._linking.issue(owner_id=owner_id, platform=PLATFORM, now=now, ttl=ttl)
        return build_authorize_url(
            client_id=self._client_id, redirect_uri=self._redirect_uri, state=state
        )

    async def complete_oauth(self, *, code: str, state: str, now: datetime) -> str:
        """Complete the OAuth callback: exchange ``code`` → identity, bind via C1 (the WRITE).

        Resolves the authorizing user's Discord id from ``code``, then binds it to the
        ``state`` token's owner through C1's ``redeem_and_bind`` — the SAME mechanism
        Telegram's ``/start`` redeem uses, so the binding shape the shared
        ``resolver.resolve`` reads is identical (the binding-symmetry invariant).

        Raises:
            LinkTokenInvalidError: A tampered / replayed / expired / wrong-platform
                ``state`` — C1 raises before any bind (fail-closed; the CSRF-class
                defence). No identity is ever bound on a bad state.
            DiscordApiError: The OAuth exchange / identity fetch failed.
        """
        user_id = await self._oauth.resolve_user_id(code)
        return self._linking.redeem_and_bind(
            plaintext_token=state, platform=PLATFORM, platform_identity=user_id, now=now
        )

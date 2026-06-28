"""Slack OAuth v2 account linking (Spec C3, D-C3-4) — the carrier, not the lifecycle.

C1 owns the linking *lifecycle* (issue → redeem → bind → resolve → unlink) and ALL its
security (C1-D-5): unguessable / sha256-at-rest / **single-use** / **short-TTL** /
**platform-bound** tokens; every violation raises
:class:`~persona_connectors.errors.LinkTokenInvalidError` (fail-closed). C3 **reuses** that
unchanged — Slack is the **third carrier** (after Telegram's deep link + Discord's OAuth),
the third validation that C1-D-5 accommodates a linking mechanism with zero C1 change (C3-R-3).

This module is only Slack's **OAuth carrier** around it (D-C3-4):

- :func:`build_authorize_url` — the ``https://slack.com/oauth/v2/authorize`` URL with **the
  C1 ``LinkToken`` carried as the OAuth ``state``** (unguessable / single-use / short-TTL /
  platform-bound = free CSRF protection).
- :class:`SlackOAuthClient` — the OAuth I/O (``code`` → ``oauth.v2.access`` →
  ``authed_user.id``). The authorizing user's Slack id is the binding identity, and it
  equals the ``message.im`` ``user`` (both workspace-scoped ``U…``).
- :class:`SlackLinkingService` — the orchestration: ``issue`` an authorize URL, and **on
  the out-of-band OAuth callback** ``complete_oauth`` exchanges the code → identity and
  binds it via C1's ``redeem_and_bind`` (the **binding WRITE**; symmetric with Telegram's
  ``/start`` redeem AND Discord's OAuth callback — all three call the SAME C1 bind, so the
  binding shape the shared ``resolver.resolve`` reads is identical by construction).

**State integrity (the CSRF-class defence):** a tampered / replayed / expired /
wrong-platform ``state`` never binds — C1's ``redeem_and_bind`` raises before any bind.

**api-free**: pure carrier logic + httpx + C1's ``LinkingService``. Credential safety
(D-C3-3): the OAuth ``client_secret`` is a ``SecretStr``, used only in the exchange body at
the call site, never logged; httpx faults are suppressed ``from None``.
"""

from __future__ import annotations

import urllib.parse
from typing import TYPE_CHECKING, Protocol, runtime_checkable

import httpx

from persona_connectors.errors import SlackApiError
from persona_connectors.slack.inbound import PLATFORM

if TYPE_CHECKING:
    from datetime import datetime, timedelta

    from pydantic import SecretStr

    from persona_connectors.domain.linking import LinkingService

__all__ = [
    "OAuthIdentityResolver",
    "SlackLinkingService",
    "SlackOAuthClient",
    "build_authorize_url",
]

_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"


def build_authorize_url(
    *, client_id: str, redirect_uri: str, state: str, scope: str = "", user_scope: str = ""
) -> str:
    """Build the Slack OAuth v2 authorize URL with the ``LinkToken`` as ``state`` (D-C3-4).

    The ``state`` IS the C1 link token — unguessable / single-use / short-TTL /
    platform-bound — so it doubles as the OAuth CSRF guard. ``scope`` / ``user_scope`` are
    the configured install/identity scopes (a deploy detail; omitted from the URL when empty).
    """
    params = {"client_id": client_id, "redirect_uri": redirect_uri, "state": state}
    if scope:
        params["scope"] = scope
    if user_scope:
        params["user_scope"] = user_scope
    return f"{_AUTHORIZE_URL}?{urllib.parse.urlencode(params, quote_via=urllib.parse.quote)}"


@runtime_checkable
class OAuthIdentityResolver(Protocol):
    """Resolve an OAuth ``code`` to the authorizing user's Slack id (the carrier I/O port)."""

    async def resolve_user_id(self, code: str) -> str:
        """Exchange ``code`` via ``oauth.v2.access`` and return ``authed_user.id``."""
        ...


class SlackOAuthClient:
    """The Slack OAuth I/O (``code`` → ``authed_user.id``) over ``httpx``.

    Holds the app credentials (``client_id`` + the ``SecretStr`` ``client_secret``) + the
    redirect URI; an injected :class:`httpx.AsyncClient` (DI). The secret is unwrapped only
    into the exchange body at the call site and never logged / surfaced; httpx faults are
    suppressed ``from None`` (D-C3-3).
    """

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: SecretStr,
        redirect_uri: str,
        http: httpx.AsyncClient,
        api_base_url: str = "https://slack.com/api",
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri
        self._http = http
        self._base = api_base_url.rstrip("/")

    async def resolve_user_id(self, code: str) -> str:
        """Exchange ``code`` via ``oauth.v2.access`` → the authorizing user's Slack id."""
        data = {
            "client_id": self._client_id,
            "client_secret": self._client_secret.get_secret_value(),
            "code": code,
            "redirect_uri": self._redirect_uri,
        }
        try:
            response = await self._http.post(f"{self._base}/oauth.v2.access", data=data)
        except httpx.HTTPError:
            raise SlackApiError(
                "slack oauth exchange failed", context={"step": "exchange"}
            ) from None
        return self._authed_user_id(response)

    @staticmethod
    def _authed_user_id(response: httpx.Response) -> str:
        """Extract ``authed_user.id`` from a successful ``oauth.v2.access`` reply."""
        if response.status_code != 200:
            raise SlackApiError(
                "slack oauth exchange rejected",
                context={"step": "exchange", "status": str(response.status_code)},
            )
        try:
            body: object = response.json()
        except ValueError:
            body = None
        if not isinstance(body, dict) or body.get("ok") is not True:
            error = str(body.get("error", "")).strip() if isinstance(body, dict) else ""
            raise SlackApiError(
                f"slack oauth rejected: {error}" if error else "slack oauth rejected",
                context={"step": "exchange", "error": error},
            )
        authed_user = body.get("authed_user")
        user_id = authed_user.get("id") if isinstance(authed_user, dict) else None
        if not isinstance(user_id, str) or not user_id:
            raise SlackApiError(
                "slack oauth response missing authed_user.id", context={"step": "exchange"}
            )
        return user_id


class SlackLinkingService:
    """Slack's OAuth carrier around C1's :class:`LinkingService` (issue link / bind).

    Holds no state beyond its injected C1 ``LinkingService`` + the OAuth resolver + the
    app's ``client_id``/``redirect_uri``/scopes. The token generation, single-use
    consumption, TTL, platform-binding, and the bind all live in C1.
    """

    def __init__(
        self,
        *,
        linking: LinkingService,
        oauth: OAuthIdentityResolver,
        client_id: str,
        redirect_uri: str,
        scope: str = "",
        user_scope: str = "",
    ) -> None:
        self._linking = linking
        self._oauth = oauth
        self._client_id = client_id
        self._redirect_uri = redirect_uri
        self._scope = scope
        self._user_scope = user_scope

    def issue_authorize_url(self, *, owner_id: str, now: datetime, ttl: timedelta) -> str:
        """Issue a one-time link for ``owner_id`` and return the Slack authorize URL."""
        state = self._linking.issue(owner_id=owner_id, platform=PLATFORM, now=now, ttl=ttl)
        return build_authorize_url(
            client_id=self._client_id,
            redirect_uri=self._redirect_uri,
            state=state,
            scope=self._scope,
            user_scope=self._user_scope,
        )

    async def complete_oauth(self, *, code: str, state: str, now: datetime) -> str:
        """Complete the OAuth callback: exchange ``code`` → identity, bind via C1 (the WRITE).

        Resolves the authorizing user's Slack id from ``code``, then binds it to the
        ``state`` token's owner through C1's ``redeem_and_bind`` — the SAME mechanism
        Telegram's ``/start`` and Discord's OAuth callback use (the binding-symmetry invariant).

        Raises:
            LinkTokenInvalidError: A tampered / replayed / expired / wrong-platform ``state``
                — C1 raises before any bind (fail-closed; the CSRF-class defence).
            SlackApiError: The OAuth exchange / identity fetch failed.
        """
        user_id = await self._oauth.resolve_user_id(code)
        return self._linking.redeem_and_bind(
            plaintext_token=state, platform=PLATFORM, platform_identity=user_id, now=now
        )

"""Discord OAuth linking (Spec C3 ⛔) — binding-symmetry + state-integrity + OAuth I/O.

The security spine of the Discord adapter. Two non-negotiables, tested against the
**real** C1 ``LinkingService`` + ``InboundIdentityResolver`` (only the persistence is a
fake in-memory store), so the Discord carrier is proven through the actual shared
resolution path — not a mock of it:

1. **Binding-shape symmetry** — the out-of-band OAuth callback writes the *identical*
   binding a Telegram ``/start`` redeem writes (both call the same C1 ``redeem_and_bind``
   → ``bind_identity``), so a Discord-linked identity resolves through the shared
   ``resolver.resolve`` exactly like a Telegram-linked one.
2. **OAuth-state integrity** (the CSRF-class boundary) — a tampered / replayed / expired
   / wrong-platform ``state`` resolves to **refusal, never a bind**.
"""

from __future__ import annotations

# ruff: noqa: ARG001, ARG002 — fakes/handlers mirror protocol signatures; some args unused.
import urllib.parse
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from persona_connectors.discord.linking import (
    DiscordLinkingService,
    DiscordOAuthClient,
    build_authorize_url,
)
from persona_connectors.domain.linking import LinkingService, LinkRecord, LinkToken
from persona_connectors.domain.normalise import NormalisedInbound
from persona_connectors.domain.resolution import (
    InboundIdentityResolver,
    ResolvedIdentity,
    UnlinkedIdentity,
)
from persona_connectors.errors import DiscordApiError, LinkTokenInvalidError
from pydantic import SecretStr

_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
_TTL = timedelta(minutes=15)
_OWNER = "owner-A"
_DISCORD_ID = "discord-777"
_SECRET = "oauth-client-secret.zzz"  # noqa: S105 — test literal


class _FakeLinkStore:
    """An in-memory ``LinkStore`` — the real lifecycle/validation runs over it."""

    def __init__(self) -> None:
        self.tokens: dict[str, LinkToken] = {}
        self.identities: dict[tuple[str, str], LinkRecord] = {}

    def create_token(self, token: LinkToken) -> None:
        self.tokens[token.token_hash] = token

    def get_token_by_hash(self, token_hash: str) -> LinkToken | None:
        return self.tokens.get(token_hash)

    def consume_token(self, token_hash: str, *, now: datetime) -> None:
        token = self.tokens[token_hash]
        self.tokens[token_hash] = token.model_copy(
            update={"status": "consumed", "consumed_at": now}
        )

    def bind_identity(
        self, *, platform: str, platform_identity: str, owner_id: str, now: datetime
    ) -> None:
        self.identities[(platform, platform_identity)] = LinkRecord(
            platform=platform,
            platform_identity=platform_identity,
            owner_id=owner_id,
            status="active",
            linked_at=now,
        )

    def get_active_identity(self, *, platform: str, platform_identity: str) -> LinkRecord | None:
        record = self.identities.get((platform, platform_identity))
        return record if record is not None and record.status == "active" else None

    def revoke_identity(
        self, *, owner_id: str, platform: str, platform_identity: str, now: datetime
    ) -> None:
        key = (platform, platform_identity)
        record = self.identities.get(key)
        if record is not None:
            self.identities[key] = record.model_copy(
                update={"status": "revoked", "revoked_at": now}
            )


class _FakeOAuth:
    """A stand-in :class:`OAuthIdentityResolver` — returns a fixed Discord id."""

    def __init__(self, user_id: str = _DISCORD_ID) -> None:
        self.user_id = user_id
        self.codes: list[str] = []

    async def resolve_user_id(self, code: str) -> str:
        self.codes.append(code)
        return self.user_id


def _service(
    store: _FakeLinkStore, oauth: _FakeOAuth | None = None
) -> tuple[DiscordLinkingService, LinkingService]:
    linking = LinkingService(store)  # the REAL C1 lifecycle
    discord = DiscordLinkingService(
        linking=linking,
        oauth=oauth or _FakeOAuth(),
        client_id="client-1",
        redirect_uri="https://app.test/discord/oauth/callback",
    )
    return discord, linking


def _state_of(authorize_url: str) -> str:
    query = urllib.parse.parse_qs(urllib.parse.urlparse(authorize_url).query)
    return query["state"][0]


def _inbound(platform: str, sender_id: str) -> NormalisedInbound:
    return NormalisedInbound(
        platform=platform,
        sender_id=sender_id,
        conversation_key="c",
        message_id="m",
        text="hi",
        received_at=_NOW,
    )


# --- the authorize URL carrier ---


def test_authorize_url_carries_state_scopes_and_redirect() -> None:
    url = build_authorize_url(
        client_id="client-1", redirect_uri="https://app.test/cb", state="STATE123"
    )
    query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert url.startswith("https://discord.com/oauth2/authorize?")
    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["client-1"]
    assert query["scope"] == ["identify bot"]  # parse_qs decodes %20 → space
    assert "identify%20bot" in url  # the wire form is percent-encoded, not '+'
    assert query["redirect_uri"] == ["https://app.test/cb"]
    assert query["state"] == ["STATE123"]


def test_issue_authorize_url_embeds_a_pending_c1_token() -> None:
    store = _FakeLinkStore()
    discord, _ = _service(store)
    url = discord.issue_authorize_url(owner_id=_OWNER, now=_NOW, ttl=_TTL)
    state = _state_of(url)
    # The state is a real C1 token, stored pending (only its hash at rest).
    assert len(store.tokens) == 1
    token = next(iter(store.tokens.values()))
    assert token.status == "pending"
    assert token.owner_id == _OWNER
    assert token.platform == "discord"
    assert state  # the plaintext rode out in the URL; the store holds only the hash


# --- binding-shape symmetry (the carried-forward invariant) ---


@pytest.mark.asyncio
async def test_oauth_binding_resolves_identically_to_a_telegram_binding() -> None:
    """A Discord-linked identity resolves through the SHARED resolver exactly like Telegram.

    Both bindings go through the same C1 ``redeem_and_bind`` → ``bind_identity``, so the
    ``LinkRecord`` the shared ``resolver.resolve`` reads is identical by construction.
    """
    store = _FakeLinkStore()
    discord, linking = _service(store)
    resolver = InboundIdentityResolver(linking)  # the REAL shared resolution gate

    # Discord: the out-of-band OAuth callback writes the binding.
    url = discord.issue_authorize_url(owner_id=_OWNER, now=_NOW, ttl=_TTL)
    bound_owner = await discord.complete_oauth(code="auth-code", state=_state_of(url), now=_NOW)
    assert bound_owner == _OWNER

    # Telegram: the inline /start redeem writes the binding (same C1 service).
    tg_token = linking.issue(owner_id=_OWNER, platform="telegram", now=_NOW, ttl=_TTL)
    linking.redeem_and_bind(
        plaintext_token=tg_token, platform="telegram", platform_identity="tg-999", now=_NOW
    )

    # The SHARED resolver resolves both to the same owner, both ResolvedIdentity.
    discord_resolution = resolver.resolve(_inbound("discord", _DISCORD_ID))
    telegram_resolution = resolver.resolve(_inbound("telegram", "tg-999"))
    assert isinstance(discord_resolution, ResolvedIdentity)
    assert isinstance(telegram_resolution, ResolvedIdentity)
    assert discord_resolution.owner_id == telegram_resolution.owner_id == _OWNER

    # And the persisted records have the identical shape (only platform/identity differ).
    discord_record = store.identities[("discord", _DISCORD_ID)]
    telegram_record = store.identities[("telegram", "tg-999")]
    assert discord_record.owner_id == telegram_record.owner_id
    assert discord_record.status == telegram_record.status == "active"


# --- OAuth-state integrity (the CSRF-class boundary) — every attack → refusal ---


@pytest.mark.asyncio
async def test_tampered_state_refuses_to_bind() -> None:
    """An attacker-chosen / unknown state never binds (unforgeable)."""
    store = _FakeLinkStore()
    discord, linking = _service(store)
    with pytest.raises(LinkTokenInvalidError):
        await discord.complete_oauth(code="auth-code", state="forged-state-xyz", now=_NOW)
    assert store.identities == {}  # nothing bound
    resolution = InboundIdentityResolver(linking).resolve(_inbound("discord", _DISCORD_ID))
    assert isinstance(resolution, UnlinkedIdentity)  # the identity is still unlinked


@pytest.mark.asyncio
async def test_replayed_state_refuses_the_second_bind() -> None:
    """A state is single-use — a replay after a successful link is refused."""
    store = _FakeLinkStore()
    discord, _ = _service(store)
    state = _state_of(discord.issue_authorize_url(owner_id=_OWNER, now=_NOW, ttl=_TTL))
    await discord.complete_oauth(code="code-1", state=state, now=_NOW)  # first use binds
    with pytest.raises(LinkTokenInvalidError):
        await discord.complete_oauth(code="code-2", state=state, now=_NOW)  # replay refused
    assert len(store.identities) == 1  # exactly one binding, not two


@pytest.mark.asyncio
async def test_expired_state_refuses_to_bind() -> None:
    """A state past its TTL never binds (expiring)."""
    store = _FakeLinkStore()
    discord, _ = _service(store)
    state = _state_of(discord.issue_authorize_url(owner_id=_OWNER, now=_NOW, ttl=_TTL))
    later = _NOW + _TTL + timedelta(seconds=1)
    with pytest.raises(LinkTokenInvalidError):
        await discord.complete_oauth(code="code-1", state=state, now=later)
    assert store.identities == {}


@pytest.mark.asyncio
async def test_wrong_platform_state_refuses_to_bind() -> None:
    """A Telegram-issued token presented on the Discord callback is platform-mismatched → refused."""  # noqa: E501
    store = _FakeLinkStore()
    discord, linking = _service(store)
    tg_state = linking.issue(owner_id=_OWNER, platform="telegram", now=_NOW, ttl=_TTL)
    with pytest.raises(LinkTokenInvalidError):
        await discord.complete_oauth(code="code-1", state=tg_state, now=_NOW)
    assert store.identities == {}


# --- the OAuth I/O client (over httpx MockTransport) ---


def _oauth_client(handler: object) -> DiscordOAuthClient:
    return DiscordOAuthClient(
        client_id="client-1",
        client_secret=SecretStr(_SECRET),
        redirect_uri="https://app.test/cb",
        http=httpx.AsyncClient(transport=httpx.MockTransport(handler)),  # type: ignore[arg-type]
        api_base_url="https://discord.test/api/v10",
    )


@pytest.mark.asyncio
async def test_resolve_user_id_exchanges_then_fetches() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v10/oauth2/token":
            return httpx.Response(200, json={"access_token": "at-1", "token_type": "Bearer"})
        assert request.headers.get("authorization") == "Bearer at-1"
        return httpx.Response(200, json={"id": "discord-777", "username": "yasin"})

    assert await _oauth_client(handler).resolve_user_id("the-code") == "discord-777"


@pytest.mark.asyncio
async def test_token_exchange_rejection_is_a_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "invalid_grant"})

    with pytest.raises(DiscordApiError):
        await _oauth_client(handler).resolve_user_id("bad-code")


@pytest.mark.asyncio
async def test_missing_access_token_is_a_domain_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"token_type": "Bearer"})  # no access_token

    with pytest.raises(DiscordApiError):
        await _oauth_client(handler).resolve_user_id("code")


@pytest.mark.asyncio
async def test_client_secret_never_leaks_on_a_transport_fault() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    with pytest.raises(DiscordApiError) as exc:
        await _oauth_client(handler).resolve_user_id("code")
    assert _SECRET not in str(exc.value)
    assert all(_SECRET not in v for v in exc.value.context.values())
    assert exc.value.__cause__ is None  # suppressed with `from None`

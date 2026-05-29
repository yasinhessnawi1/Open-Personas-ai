"""Authentication seam + the RLS-scoped current-user dependency (spec 08, T05).

The API does not implement signup/login/sessions — a third-party provider
(Clerk or Supabase; S08-1 deferred, D-08-4) issues JWTs. The API validates the
token on every request, extracts the user id, and — critically — sets it on the
:data:`persona_api.middleware.rls_context.current_user_id` ``ContextVar`` so the
RLS pool listener scopes every connection (D-08-1).

The verification is an **injectable seam** (``verify_token``): the default uses
``python-jose`` (HS256 for the test fake-JWT path, RS256 for the real JWKS path;
fail-closed on expired/tampered/wrong-audience — verified research §4). Tests
override the ``verify_token`` dependency with a fake verifier so no provider is
called (acceptance #14). Deferring the provider keeps the seam provider-agnostic
(both issue JWTs).
"""

from __future__ import annotations

# NOTE: these collections.abc names are imported at RUNTIME (not under
# TYPE_CHECKING) because FastAPI resolves dependency signatures via
# get_type_hints at startup — with `from __future__ import annotations` every
# annotation is a string, so every name in a dependency's signature must be
# importable at runtime or FastAPI mis-reads the params as query params.
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import TYPE_CHECKING

from fastapi import Depends, Request
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict

from persona_api.errors import AuthenticationError
from persona_api.middleware.rls_context import current_user_id

if TYPE_CHECKING:
    from persona_api.config import APIConfig

__all__ = [
    "AuthenticatedUser",
    "get_current_user",
    "get_verify_token",
    "make_jwt_verifier",
]


class AuthenticatedUser(BaseModel):
    """The authenticated principal extracted from a verified token."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    email: str | None = None


# A verifier is `Callable[[str], Awaitable[AuthenticatedUser]]` — takes the raw
# bearer token, returns the authenticated user, or raises AuthenticationError.
# Async so a real provider can do a network JWKS fetch; the default does no I/O.


def _bearer_token(request: Request) -> str:
    """Extract the bearer token from the Authorization header, or 401."""
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise AuthenticationError("missing or malformed Authorization header")
    token = header.removeprefix("Bearer ").strip()
    if not token:
        raise AuthenticationError("empty bearer token")
    return token


# Algorithm families. The key MUST be bound to the family per the token's own
# `alg` header, NEVER chosen independently of it — otherwise an attacker who has
# the (public) RSA/EC key can forge an HS256 token signed with that key as the
# HMAC secret (the classic JWT algorithm-confusion attack). Security-reviewer
# HIGH finding (spec 08 T05): bind key↔alg, and reject a public key paired with
# an HMAC alg (and vice versa) at construction (fail-fast).
_SYMMETRIC_ALGS = frozenset({"HS256", "HS384", "HS512"})
_ASYMMETRIC_ALGS = frozenset(
    {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512"}
)


def make_jwt_verifier(config: APIConfig) -> Callable[[str], Awaitable[AuthenticatedUser]]:
    """Build the default ``python-jose`` JWT verifier from config (D-08-4).

    HMAC algorithms verify against the symmetric ``jwt_secret``; RSA/EC
    algorithms verify against the asymmetric ``jwt_public_key``. The key is
    selected **per the verified token's own algorithm family** — never
    independently — so a public key can never be used as an HMAC secret
    (algorithm-confusion attack). A configured algorithm whose key is missing is
    rejected at construction (fail-fast). Fails closed on any
    signature/expiry/audience failure. The ``sub`` claim is the user id.
    """
    secret = config.jwt_secret.get_secret_value() if config.jwt_secret else None
    public_key = config.jwt_public_key.get_secret_value() if config.jwt_public_key else None
    algorithms = config.jwt_algorithms_list
    audience = config.jwt_audience or None

    # Partition configured algorithms by family and pair each with its key.
    sym_algs = [a for a in algorithms if a in _SYMMETRIC_ALGS]
    asym_algs = [a for a in algorithms if a in _ASYMMETRIC_ALGS]
    unknown = [a for a in algorithms if a not in _SYMMETRIC_ALGS and a not in _ASYMMETRIC_ALGS]
    if unknown:
        msg = f"unsupported JWT algorithm(s): {unknown}"
        raise ValueError(msg)
    if sym_algs and not secret:
        msg = f"HMAC algorithm(s) {sym_algs} configured but PERSONA_API_JWT_SECRET is unset"
        raise ValueError(msg)
    if asym_algs and not public_key:
        msg = (
            f"asymmetric algorithm(s) {asym_algs} configured but "
            "PERSONA_API_JWT_PUBLIC_KEY is unset"
        )
        raise ValueError(msg)
    if not sym_algs and not asym_algs:
        msg = "no usable JWT algorithm/key pair configured"
        raise ValueError(msg)

    async def _verify(token: str) -> AuthenticatedUser:
        # Read the token's claimed alg from the (unverified) header, pick the
        # matching family's key, and verify ONLY against that family's algs.
        try:
            header_alg = jwt.get_unverified_header(token).get("alg")
        except JWTError as exc:
            raise AuthenticationError(
                "malformed token header", context={"reason": str(exc)}
            ) from exc
        if header_alg in _SYMMETRIC_ALGS and header_alg in sym_algs:
            key, allowed = secret, sym_algs
        elif header_alg in _ASYMMETRIC_ALGS and header_alg in asym_algs:
            key, allowed = public_key, asym_algs
        else:
            raise AuthenticationError(
                "token algorithm not allowed", context={"alg": str(header_alg)}
            )
        try:
            claims = jwt.decode(
                token,
                key,
                algorithms=allowed,
                audience=audience,
                options={"verify_aud": audience is not None},
            )
        except JWTError as exc:
            raise AuthenticationError("invalid token", context={"reason": str(exc)}) from exc
        sub = claims.get("sub")
        if not sub:
            raise AuthenticationError("token missing 'sub' claim")
        return AuthenticatedUser(id=str(sub), email=claims.get("email"))

    return _verify


def get_verify_token(request: Request) -> Callable[[str], Awaitable[AuthenticatedUser]]:
    """Provide the active token verifier.

    The default is built from the app's :class:`APIConfig` (stored on
    ``app.state.config`` by the factory). Tests override THIS dependency to
    inject a fake-JWT verifier (no provider call). Kept as a dependency (not a
    bare import) precisely so it is overridable.
    """
    verifier = getattr(request.app.state, "verify_token", None)
    if verifier is not None:
        return verifier  # type: ignore[no-any-return]
    return make_jwt_verifier(request.app.state.config)


async def get_current_user(
    request: Request,
    verify: Callable[[str], Awaitable[AuthenticatedUser]] = Depends(get_verify_token),
) -> AsyncIterator[AuthenticatedUser]:
    """Authenticate the request and bind the RLS user-id for its duration (D-08-1).

    A ``yield`` dependency so the :data:`current_user_id` ``ContextVar`` lifetime
    is exactly the request scope: extract + verify the bearer token, **set** the
    contextvar (so the RLS pool listener scopes every connection this request
    touches — route queries AND the runtime store's), yield the user, then
    **reset** the contextvar on teardown so nothing leaks to a later request on
    the same worker. On auth failure the contextvar is never set (fail-closed —
    an unscoped connection sees zero rows).
    """
    token = _bearer_token(request)
    user = await verify(token)
    # JIT-provision the users row: the provider (Clerk) issues JWTs but the API
    # has no signup, and persona/conversation/run/credits all FK users.id
    # (webhook mirroring deferred in spec 08). A system action on the superuser
    # engine; idempotent. None in unit tests without a superuser DSN.
    admin_engine = getattr(request.app.state, "admin_engine", None)
    if admin_engine is not None:
        from persona_api.services.user_service import ensure_user

        ensure_user(admin_engine, user_id=user.id, email=user.email)
    reset_token = current_user_id.set(user.id)
    try:
        yield user
    finally:
        current_user_id.reset(reset_token)

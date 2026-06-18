"""Unit tests for the auth verification seam (spec 08, T05, D-08-4).

No DB. Mount a tiny app with a route guarded by ``get_current_user``, override
the ``verify_token`` seam with a fake verifier (the acceptance-#14 pattern), and
assert: a valid token resolves the user; a missing/invalid token → 401; the
default python-jose verifier round-trips an HS256 token and fails closed.
"""

from __future__ import annotations

import time

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from jose import jwt
from persona_api.auth import (
    AuthenticatedUser,
    get_current_user,
    get_verify_token,
    make_jwt_verifier,
)
from persona_api.config import APIConfig
from persona_api.editions import CloudOwnerResolver
from persona_api.errors import register_exception_handlers


def _app_with_fake_verifier() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    async def _fake_verify(token: str) -> AuthenticatedUser:
        if token == "good":
            return AuthenticatedUser(id="user_fake", email="f@x.test")
        from persona_api.errors import AuthenticationError

        raise AuthenticationError("bad token")

    app.state.verify_token = _fake_verify
    # Spec 33: get_current_user delegates to the edition's OwnerResolver. This
    # suite exercises the cloud path (verify the bearer JWT → owner).
    app.state.owner_resolver = CloudOwnerResolver()

    @app.get("/me")
    async def _me(user: AuthenticatedUser = Depends(get_current_user)) -> dict[str, str | None]:
        return {"id": user.id, "email": user.email}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app_with_fake_verifier())


def test_valid_token_resolves_user(client: TestClient) -> None:
    resp = client.get("/me", headers={"Authorization": "Bearer good"})
    assert resp.status_code == 200
    assert resp.json() == {"id": "user_fake", "email": "f@x.test"}


def test_missing_header_is_401(client: TestClient) -> None:
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "authentication_error"
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_malformed_header_is_401(client: TestClient) -> None:
    resp = client.get("/me", headers={"Authorization": "Token good"})
    assert resp.status_code == 401


def test_invalid_token_is_401(client: TestClient) -> None:
    resp = client.get("/me", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 401


def test_verify_token_override_is_used_not_default() -> None:
    # The seam (get_verify_token) returns the app.state override when present.
    app = _app_with_fake_verifier()
    from starlette.requests import Request

    scope = {"type": "http", "app": app, "headers": []}
    verifier = get_verify_token(Request(scope))  # type: ignore[arg-type]
    assert verifier is app.state.verify_token


def test_default_jwt_verifier_hs256_round_trip() -> None:
    cfg = APIConfig(jwt_secret="s3cret", jwt_algorithms="HS256")
    verify = make_jwt_verifier(cfg)
    token = jwt.encode(
        {"sub": "u1", "email": "a@x.test", "exp": int(time.time()) + 60},
        "s3cret",
        algorithm="HS256",
    )
    import asyncio

    user = asyncio.run(verify(token))
    assert user.id == "u1"
    assert user.email == "a@x.test"


def test_default_jwt_verifier_fails_closed_on_tamper() -> None:
    cfg = APIConfig(jwt_secret="s3cret", jwt_algorithms="HS256")
    verify = make_jwt_verifier(cfg)
    import asyncio

    from persona_api.errors import AuthenticationError

    with pytest.raises(AuthenticationError):
        asyncio.run(verify("not.a.jwt"))


def test_default_jwt_verifier_requires_sub() -> None:
    cfg = APIConfig(jwt_secret="s3cret", jwt_algorithms="HS256")
    verify = make_jwt_verifier(cfg)
    token = jwt.encode(
        {"email": "a@x.test", "exp": int(time.time()) + 60}, "s3cret", algorithm="HS256"
    )
    import asyncio

    from persona_api.errors import AuthenticationError

    with pytest.raises(AuthenticationError):
        asyncio.run(verify(token))


def _rsa_keypair() -> tuple[str, str]:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    pub = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    return priv, pub


def test_rs256_verifier_accepts_a_real_rs256_token() -> None:
    priv, pub = _rsa_keypair()
    cfg = APIConfig(jwt_public_key=pub, jwt_algorithms="RS256")
    verify = make_jwt_verifier(cfg)
    token = jwt.encode({"sub": "u1", "exp": int(time.time()) + 60}, priv, algorithm="RS256")
    import asyncio

    assert asyncio.run(verify(token)).id == "u1"


def _forge_hs256(payload: dict[str, object], hmac_secret: str) -> str:
    """Hand-craft an HS256 JWT (an attacker would NOT use jose, which guards its
    own encode; they HMAC the signing input with the public-key bytes directly).
    """
    import base64
    import hashlib
    import hmac
    import json

    def b64(raw: bytes) -> str:
        return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

    header = b64(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = b64(json.dumps(payload).encode())
    signing_input = f"{header}.{body}".encode()
    sig = hmac.new(hmac_secret.encode(), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{b64(sig)}"


def test_rs256_verifier_rejects_hs256_token_forged_with_public_key() -> None:
    # The algorithm-confusion attack (security-reviewer finding): an attacker who
    # has the (public) RSA key forges an HS256 token, HMAC-signing the signing
    # input with the public-key bytes. An RS256-configured verifier MUST reject
    # it. python-jose ALSO guards this at decode (it refuses a PEM as an HMAC
    # secret), so the specific PEM vector is doubly-blocked — but our verifier
    # binds key↔alg-family explicitly so the guarantee does not depend on the
    # library's incidental key-type detection (defense-in-depth). We forge by
    # hand to simulate the attacker faithfully.
    import asyncio

    from persona_api.errors import AuthenticationError

    _priv, pub = _rsa_keypair()
    cfg = APIConfig(jwt_public_key=pub, jwt_algorithms="RS256")
    verify = make_jwt_verifier(cfg)
    forged = _forge_hs256({"sub": "victim", "exp": int(time.time()) + 60}, pub)
    with pytest.raises(AuthenticationError):
        asyncio.run(verify(forged))


def test_verifier_construction_fails_fast_on_alg_without_key() -> None:
    # RS256 configured but no public key → refuse to build (fail-fast), rather
    # than silently fall back to the HMAC secret (the confusion vector).
    with pytest.raises(ValueError, match="PUBLIC_KEY"):
        make_jwt_verifier(APIConfig(jwt_secret="s3cret", jwt_algorithms="RS256"))
    with pytest.raises(ValueError, match="SECRET"):
        make_jwt_verifier(APIConfig(jwt_public_key="-----X-----", jwt_algorithms="HS256"))


def test_verifier_rejects_unknown_algorithm() -> None:
    with pytest.raises(ValueError, match="unsupported JWT algorithm"):
        make_jwt_verifier(APIConfig(jwt_secret="s3cret", jwt_algorithms="none"))

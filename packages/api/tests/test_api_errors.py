"""Unit tests for the exception handlers (spec 08, T02).

Mount a tiny app whose routes raise each domain exception, then assert the
handler maps it to the right status + structured body. No DB.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from persona.errors import PersonaNotFoundError, SchemaVersionMismatchError, ToolNotAllowedError
from persona_api.errors import (
    AuthenticationError,
    ConversationNotFoundError,
    CreditsExhaustedError,
    RateLimitExceededError,
    RunNotFoundError,
    register_exception_handlers,
)
from pydantic import BaseModel


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/auth")
    async def _auth() -> None:
        raise AuthenticationError("no token")

    @app.get("/credits")
    async def _credits() -> None:
        raise CreditsExhaustedError("broke", context={"balance": "0"})

    @app.get("/tool")
    async def _tool() -> None:
        raise ToolNotAllowedError("nope", context={"allowed": "web_search"})

    @app.get("/persona")
    async def _persona() -> None:
        raise PersonaNotFoundError("missing", context={"id": "p1"})

    @app.get("/conv")
    async def _conv() -> None:
        raise ConversationNotFoundError()

    @app.get("/run")
    async def _run() -> None:
        raise RunNotFoundError()

    @app.get("/rate")
    async def _rate() -> None:
        raise RateLimitExceededError(
            "slow down",
            context={"limit": "20", "remaining": "0", "reset": "1700000000"},
        )

    @app.get("/schema")
    async def _schema() -> None:
        raise SchemaVersionMismatchError("bad version")

    class Body(BaseModel):
        n: int

    @app.post("/validate")
    async def _validate(body: Body) -> dict[str, int]:
        return {"n": body.n}

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app())


@pytest.mark.parametrize(
    ("path", "code", "error"),
    [
        ("/auth", 401, "authentication_error"),
        ("/credits", 402, "credits_exhausted"),
        ("/tool", 403, "tool_not_allowed"),
        ("/persona", 404, "persona_not_found"),
        ("/conv", 404, "conversation_not_found"),
        ("/run", 404, "run_not_found"),
        ("/rate", 429, "rate_limit_exceeded"),
        ("/schema", 422, "schema_version_mismatch"),
    ],
)
def test_exception_maps_to_status_and_body(
    client: TestClient, path: str, code: int, error: str
) -> None:
    resp = client.get(path)
    assert resp.status_code == code
    assert resp.json()["error"] == error


def test_auth_sets_www_authenticate_header(client: TestClient) -> None:
    resp = client.get("/auth")
    assert resp.headers["WWW-Authenticate"] == "Bearer"


def test_rate_limit_sets_headers(client: TestClient) -> None:
    resp = client.get("/rate")
    assert resp.headers["X-RateLimit-Limit"] == "20"
    assert resp.headers["X-RateLimit-Remaining"] == "0"
    assert resp.headers["X-RateLimit-Reset"] == "1700000000"
    assert "Retry-After" in resp.headers


def test_context_appears_in_body(client: TestClient) -> None:
    resp = client.get("/tool")
    assert resp.json()["context"] == {"allowed": "web_search"}


def test_invalid_body_returns_structured_422(client: TestClient) -> None:
    resp = client.post("/validate", json={"n": "not-an-int"})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "validation_error"
    assert isinstance(body["detail"], list)

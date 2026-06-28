"""The Slack OAuth ASGI app (Spec C3 ⛔) — issue-route authz + callback fail-closed.

Asserts: the issue route derives the owner from the verified JWT (never the body); the OAuth
callback binds on a good state but fails closed (400, no bind) on a bad state / failed
exchange — never an attacker-chosen binding (the CSRF-class boundary, D-C3-4).
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from persona.auth.jwt_verifier import AuthenticatedUser
from persona.errors import AuthenticationError
from persona_connectors.errors import LinkTokenInvalidError, SlackApiError
from persona_connectors.slack.app import build_slack_app

_ISSUE = "/v1/connectors/slack/link"
_CALLBACK = "/slack/oauth/callback"


def _app(
    *,
    issued_for: list[str] | None = None,
    completed: list[tuple[str, str]] | None = None,
    jwt_owner: str | None = "user_from_token",
) -> TestClient:
    issued = issued_for if issued_for is not None else []
    done = completed if completed is not None else []

    async def issue_authorize_url(owner_id: str) -> str:
        issued.append(owner_id)
        return f"https://slack.com/oauth/v2/authorize?client_id=c&state=token_for_{owner_id}"

    async def complete_oauth(code: str, state: str) -> str:
        if state == "bad-state":
            raise LinkTokenInvalidError("invalid state", context={"platform": "slack"})
        if code == "fail-exchange":
            raise SlackApiError("oauth exchange failed", context={"step": "exchange"})
        done.append((code, state))
        return "owner-bound"

    async def verify_jwt(token: str) -> AuthenticatedUser:
        if jwt_owner is None or token == "bad":
            raise AuthenticationError("invalid token")
        return AuthenticatedUser(id=jwt_owner, email=None)

    app = build_slack_app(
        issue_authorize_url=issue_authorize_url,
        complete_oauth=complete_oauth,
        verify_jwt=verify_jwt,
    )
    return TestClient(app)


def test_issue_derives_owner_from_verified_jwt_not_body() -> None:
    issued: list[str] = []
    client = _app(issued_for=issued, jwt_owner="real_owner")
    resp = client.post(
        _ISSUE,
        json={"owner_id": "attacker_chosen_owner"},
        headers={"Authorization": "Bearer good"},
    )
    assert resp.status_code == 200
    assert resp.json()["authorize_url"].endswith("state=token_for_real_owner")
    assert issued == ["real_owner"]


def test_issue_requires_a_bearer_token() -> None:
    assert _app().post(_ISSUE, json={}).status_code == 401


def test_issue_rejects_an_invalid_jwt() -> None:
    issued: list[str] = []
    resp = _app(issued_for=issued).post(_ISSUE, json={}, headers={"Authorization": "Bearer bad"})
    assert resp.status_code == 401
    assert issued == []


def test_callback_binds_on_a_good_state() -> None:
    completed: list[tuple[str, str]] = []
    resp = _app(completed=completed).get(
        _CALLBACK, params={"code": "auth-code", "state": "good-state"}
    )
    assert resp.status_code == 200
    assert "linked" in resp.text.lower()
    assert completed == [("auth-code", "good-state")]


def test_callback_bad_state_fails_closed_no_bind() -> None:
    completed: list[tuple[str, str]] = []
    resp = _app(completed=completed).get(
        _CALLBACK, params={"code": "auth-code", "state": "bad-state"}
    )
    assert resp.status_code == 400
    assert "didn't work" in resp.text.lower()
    assert completed == []


def test_callback_missing_params_fails_closed() -> None:
    completed: list[tuple[str, str]] = []
    resp = _app(completed=completed).get(_CALLBACK, params={"code": "auth-code"})
    assert resp.status_code == 400
    assert completed == []


def test_callback_failed_exchange_fails_closed() -> None:
    resp = _app().get(_CALLBACK, params={"code": "fail-exchange", "state": "good-state"})
    assert resp.status_code == 400

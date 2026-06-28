"""The Slack HTTP-events app (Spec C3 ⛔) — verify-before-parse + challenge + dispatch.

Driven through FastAPI's TestClient. Asserts: a validly-signed request dispatches the inner
event; a bad signature → 403 BEFORE the body is parsed (an invalid-JSON body with a bad
signature still 403s, not 400); the ``url_verification`` challenge is echoed (still signed).
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from persona_connectors.slack.events import build_events_app
from persona_connectors.slack.signing import SLACK_SIGNATURE_HEADER, SLACK_TIMESTAMP_HEADER
from pydantic import SecretStr

_SECRET = "events-signing-secret"  # noqa: S105 — test literal
_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
_TS = str(int(_NOW.timestamp()))
_EVENTS = "/slack/events"


def _sign(timestamp: str, body: bytes) -> str:
    base = f"v0:{timestamp}:".encode() + body
    return "v0=" + hmac.new(_SECRET.encode("utf-8"), base, hashlib.sha256).hexdigest()


def _app(received: list[dict[str, object]] | None = None) -> TestClient:
    got = received if received is not None else []

    async def on_event(event: dict[str, object]) -> None:
        got.append(event)

    app = build_events_app(signing_secret=SecretStr(_SECRET), on_event=on_event, now=lambda: _NOW)
    return TestClient(app)


def _post(
    client: TestClient, body: bytes, *, signature: str | None = None, ts: str = _TS
) -> object:
    sig = signature if signature is not None else _sign(ts, body)
    return client.post(
        _EVENTS,
        content=body,
        headers={SLACK_SIGNATURE_HEADER: sig, SLACK_TIMESTAMP_HEADER: ts},
    )


def test_signed_event_callback_dispatches() -> None:
    received: list[dict[str, object]] = []
    client = _app(received)
    body = b'{"type":"event_callback","event":{"type":"message","text":"hi"}}'
    resp = _post(client, body)
    assert resp.status_code == 200
    assert received == [{"type": "message", "text": "hi"}]


def test_bad_signature_rejected_before_parsing() -> None:
    """A wrong signature → 403, and the body is NEVER parsed (validate-before-parse)."""
    received: list[dict[str, object]] = []
    client = _app(received)
    # Deliberately invalid JSON: a post-parse check would 400; a 403 proves the sig gate is first.
    resp = client.post(
        _EVENTS,
        content=b"this is not json",
        headers={SLACK_SIGNATURE_HEADER: "v0=bad", SLACK_TIMESTAMP_HEADER: _TS},
    )
    assert resp.status_code == 403
    assert received == []


def test_url_verification_challenge_is_echoed() -> None:
    client = _app()
    body = b'{"type":"url_verification","challenge":"abc123"}'
    resp = _post(client, body)
    assert resp.status_code == 200
    assert resp.json()["challenge"] == "abc123"


def test_stale_timestamp_rejected() -> None:
    received: list[dict[str, object]] = []
    client = _app(received)
    old_ts = str(int(_NOW.timestamp()) - 600)
    body = b'{"type":"event_callback","event":{"type":"message"}}'
    resp = _post(client, body, ts=old_ts)
    assert resp.status_code == 403
    assert received == []

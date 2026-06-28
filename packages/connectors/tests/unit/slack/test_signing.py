"""Slack request-signing verification (Spec C3 ⛔) — the per-request trust boundary.

The load-bearing security: a forged signature → reject, a stale/replayed timestamp (>5 min)
→ reject, a tampered body → reject, an unset secret → reject (fail-closed). The signature is
computed over the RAW body bytes, constant-time-compared.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime

from persona_connectors.slack.signing import verify_slack_signature
from pydantic import SecretStr

_SECRET = "slack-signing-secret"  # noqa: S105 — test literal
_SECRET_OBJ = SecretStr(_SECRET)  # module-level singleton (avoids a call in arg defaults)
_NOW = datetime(2026, 6, 27, 12, 0, 0, tzinfo=UTC)
_TS = str(int(_NOW.timestamp()))


def _sign(secret: str, timestamp: str, body: bytes) -> str:
    """Produce a valid signature exactly as Slack does (over the RAW body)."""
    base = f"v0:{timestamp}:".encode() + body
    digest = hmac.new(secret.encode("utf-8"), base, hashlib.sha256).hexdigest()
    return f"v0={digest}"


def _verify(
    *,
    secret: SecretStr | None = _SECRET_OBJ,
    timestamp: str | None = _TS,
    body: bytes = b'{"type":"event_callback"}',
    signature: str | None = None,
    now: datetime = _NOW,
) -> bool:
    sig = signature if signature is not None else _sign(_SECRET, timestamp or "", body)
    return verify_slack_signature(
        secret, timestamp=timestamp, raw_body=body, signature=sig, now=now
    )


def test_valid_signature_accepts() -> None:
    assert _verify() is True


def test_forged_signature_rejects() -> None:
    assert _verify(signature="v0=deadbeef") is False


def test_tampered_body_rejects() -> None:
    """A signature valid for one body must not validate a different body (the whole point)."""
    good_sig = _sign(_SECRET, _TS, b'{"type":"event_callback"}')
    assert (
        verify_slack_signature(
            SecretStr(_SECRET),
            timestamp=_TS,
            raw_body=b'{"type":"event_callback","tampered":true}',
            signature=good_sig,
            now=_NOW,
        )
        is False
    )


def test_stale_timestamp_rejects() -> None:
    """A timestamp older than the 5-minute replay window → reject (a captured replay)."""
    old_ts = str(int(_NOW.timestamp()) - 301)
    assert _verify(timestamp=old_ts) is False


def test_far_future_timestamp_rejects() -> None:
    future_ts = str(int(_NOW.timestamp()) + 301)
    assert _verify(timestamp=future_ts) is False


def test_fresh_timestamp_within_window_accepts() -> None:
    recent_ts = str(int(_NOW.timestamp()) - 60)  # 1 min ago, within 5 min
    assert _verify(timestamp=recent_ts) is True


def test_unset_secret_fails_closed() -> None:
    assert _verify(secret=None) is False


def test_missing_headers_fail_closed() -> None:
    assert _verify(timestamp=None) is False
    assert _verify(signature="") is False  # empty header value is not a valid signature
    assert (
        verify_slack_signature(
            SecretStr(_SECRET), timestamp=_TS, raw_body=b"{}", signature=None, now=_NOW
        )
        is False
    )


def test_non_numeric_timestamp_rejects() -> None:
    assert _verify(timestamp="not-a-number") is False


def test_wrong_secret_rejects() -> None:
    """A signature from a different secret → reject (constant-time compare still fails)."""
    sig = _sign("a-different-secret", _TS, b"{}")
    assert (
        verify_slack_signature(
            SecretStr(_SECRET), timestamp=_TS, raw_body=b"{}", signature=sig, now=_NOW
        )
        is False
    )

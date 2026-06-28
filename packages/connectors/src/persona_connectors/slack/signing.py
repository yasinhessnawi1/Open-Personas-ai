"""Slack request-signing verification (Spec C3 ⛔, D-C3-3) — the HTTP-events security gate.

**This is the opposite trust model from Discord's gateway.** Discord's connection is
authenticated once (the bot token over TLS) and every event on it is trusted. Slack's HTTP
Events API signs **every request**: ``X-Slack-Signature`` = ``v0=``HMAC-SHA256(signing_secret,
``v0:{timestamp}:{raw_body}``) plus ``X-Slack-Request-Timestamp``. So the trust boundary is
**per-request** — verify the HMAC AND enforce a replay window. A Discord-ported "trust the
connection" assumption here would be a real vulnerability, which is why this is its own gate.

Three load-bearing properties:

1. **Sign over the RAW body bytes** — NOT re-serialized JSON. Re-serialization changes the
   bytes and the signature won't match; the base string is exactly ``v0:{timestamp}:{raw_body}``.
2. **Constant-time compare** (:func:`hmac.compare_digest`), never ``==`` (a plain compare
   leaks the signature a byte at a time via timing).
3. **Replay defence + fail-closed** — reject a timestamp older than 5 minutes (a captured
   request can't be replayed later); reject when no secret is configured (a public endpoint
   with no signature check that accepts everything is the hole this exists to prevent), or a
   header is absent.

Pure + api-free.
"""

from __future__ import annotations

import hashlib
import hmac
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import datetime

    from pydantic import SecretStr

__all__ = [
    "SLACK_SIGNATURE_HEADER",
    "SLACK_TIMESTAMP_HEADER",
    "verify_slack_signature",
]

# The headers Slack sends the signature + timestamp in on every HTTP-events request.
SLACK_SIGNATURE_HEADER = "X-Slack-Signature"
SLACK_TIMESTAMP_HEADER = "X-Slack-Request-Timestamp"

# The replay window: a request whose timestamp is older than this is rejected (5 min, Slack's
# documented guidance).
_MAX_AGE_SECONDS = 300
_VERSION = "v0"


def verify_slack_signature(
    signing_secret: SecretStr | None,
    *,
    timestamp: str | None,
    raw_body: bytes,
    signature: str | None,
    now: datetime,
    max_age_seconds: int = _MAX_AGE_SECONDS,
) -> bool:
    """Whether an HTTP-events request's signature is valid (D-C3-3).

    Args:
        signing_secret: The configured signing secret (a ``SecretStr``), or ``None`` if none
            is configured (fail-closed).
        timestamp: The ``X-Slack-Request-Timestamp`` header (Unix seconds), or ``None``.
        raw_body: The **exact raw request body bytes** (never re-serialized JSON).
        signature: The ``X-Slack-Signature`` header (``v0=…``), or ``None``.
        now: Tz-aware UTC time (injected) — the replay window is measured against it.
        max_age_seconds: The replay window (default 300 s).

    Returns:
        ``True`` only when a secret IS configured AND the timestamp is fresh AND the
        constant-time HMAC of ``v0:{timestamp}:{raw_body}`` matches the presented signature.
        **Fail-closed** on any missing input / stale timestamp / mismatch.
    """
    if signing_secret is None or timestamp is None or signature is None:
        return False  # fail-closed: no secret / no headers → reject
    try:
        request_ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(now.timestamp()) - request_ts) > max_age_seconds:
        return False  # replay window: a stale (or far-future) timestamp is rejected

    # The base string signs over the RAW body bytes — never a re-serialized form.
    base = f"{_VERSION}:{timestamp}:".encode() + raw_body
    digest = hmac.new(
        signing_secret.get_secret_value().encode("utf-8"), base, hashlib.sha256
    ).hexdigest()
    expected = f"{_VERSION}={digest}"
    return hmac.compare_digest(expected, signature)

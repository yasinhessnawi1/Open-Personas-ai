"""The Slack HTTP Events API app (Spec C3 ⛔, D-C3-2/D-C3-3) — the signed inbound endpoint.

The HTTP-events transport (the alternative to socket mode): a public ``POST /slack/events``
endpoint. **Security (D-C3-3):** it verifies the ``X-Slack-Signature`` over the **raw body**
(constant-time, with a 5-minute replay window, fail-closed on an unset secret) **before** the
body is parsed, then handles the Slack envelope:

- ``url_verification`` — the one-time endpoint handshake: echo the ``challenge`` (so Slack
  can confirm the URL). The signature is still verified first.
- ``event_callback`` — the real events: the inner ``event`` (a ``message.im``) is handed to
  the injected ``on_event`` (the flow, which classify-DM-filters).

api-free (every dependency injected). Selected by ``slack_transport=http``; socket mode
(``slack/socket.py``) is the default.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from persona_connectors.slack.signing import (
    SLACK_SIGNATURE_HEADER,
    SLACK_TIMESTAMP_HEADER,
    verify_slack_signature,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from pydantic import SecretStr

__all__ = ["build_events_app"]

_EVENTS_PATH = "/slack/events"


def build_events_app(
    *,
    signing_secret: SecretStr | None,
    on_event: Callable[[dict[str, object]], Awaitable[None]],
    now: Callable[[], datetime],
) -> FastAPI:
    """Build the Slack HTTP-events ASGI app from injected dependencies (api-free).

    Args:
        signing_secret: The Slack signing secret (``None`` ⇒ every request is rejected —
            fail-closed, D-C3-3).
        on_event: The inbound-event handler (the flow, wired by composition).
        now: A tz-aware UTC clock (injected) — the replay window is measured against it.
    """
    app = FastAPI(title="persona-connectors (slack events)")

    @app.post(_EVENTS_PATH)
    async def slack_events(request: Request) -> JSONResponse:
        # SECURITY (D-C3-3): verify the signature over the RAW body BEFORE parsing, so
        # unauthenticated input never reaches the JSON parser. Fail-closed on an unset secret.
        raw = await request.body()
        if not verify_slack_signature(
            signing_secret,
            timestamp=request.headers.get(SLACK_TIMESTAMP_HEADER),
            raw_body=raw,
            signature=request.headers.get(SLACK_SIGNATURE_HEADER),
            now=now(),
        ):
            return JSONResponse({"detail": "forbidden"}, status_code=403)

        try:
            payload = json.loads(raw)
        except ValueError:
            return JSONResponse({"detail": "invalid JSON"}, status_code=400)
        if not isinstance(payload, dict):
            return JSONResponse({"detail": "payload must be an object"}, status_code=400)

        if payload.get("type") == "url_verification":
            challenge = payload.get("challenge")
            return JSONResponse({"challenge": challenge if isinstance(challenge, str) else ""})

        if payload.get("type") == "event_callback":
            event = payload.get("event")
            if isinstance(event, dict):
                await on_event(event)
        # Always 200 on an accepted (signed) request — Slack retries on a non-2xx; processing
        # faults are handled inside the flow, not by failing the endpoint.
        return JSONResponse({"ok": True})

    return app

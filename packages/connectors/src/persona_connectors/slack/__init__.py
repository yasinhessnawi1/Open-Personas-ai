"""The Slack connector adapter (Spec C3) — a thin DM adapter on the C1 framework.

A deliberately **thin** adapter implementing C1's ``Connector`` for Slack: it converts
Slack ``message.im`` events to C1's ``NormalisedInbound`` (DMs only — D-C3-5), lets the
**shared** inbound flow drive the reply
(:class:`~persona_connectors.domain.flow.SharedInboundFlow`), and renders C1's
``NormalisedOutbound`` back as Slack mrkdwn messages — plus Slack's OAuth account-linking
carrier and its event transport (socket mode by default; HTTP events with per-request
signing behind a config seam). Everything else — routing, persona selection, the
conversation model, identity mapping, C0 delivery — is C1's and is *used*, not reimplemented.

**Slack DMs are unconditional** (the app is installed in the workspace), so — unlike
Discord — the connector has no DM-ability/cannot-deliver gate. The whole adapter is
**api-free** (httpx + ``websockets`` + persona-core contracts only); the api-coupling
lives in :mod:`persona_connectors.composition` (the reversibility guarantee, C1-D-1).
"""

from __future__ import annotations

from persona_connectors.slack.app import build_slack_app
from persona_connectors.slack.client import SLACK_MAX_MESSAGE_CHARS, SlackClient
from persona_connectors.slack.connector import SLACK_CAPABILITIES, SlackConnector
from persona_connectors.slack.events import build_events_app
from persona_connectors.slack.flow import InboundFlow
from persona_connectors.slack.inbound import (
    PLATFORM,
    InboundIgnore,
    InboundNonText,
    InboundText,
    NormalisedEvent,
    SlackNonTextKind,
    classify_event,
)
from persona_connectors.slack.linking import (
    OAuthIdentityResolver,
    SlackLinkingService,
    SlackOAuthClient,
    build_authorize_url,
)
from persona_connectors.slack.non_text import decline_message
from persona_connectors.slack.render import render_outbound
from persona_connectors.slack.signing import (
    SLACK_SIGNATURE_HEADER,
    SLACK_TIMESTAMP_HEADER,
    verify_slack_signature,
)
from persona_connectors.slack.socket import (
    SlackSocketClient,
    SlackSocketConnection,
    build_ack,
    interpret_envelope,
)

__all__ = [
    "PLATFORM",
    "SLACK_CAPABILITIES",
    "SLACK_MAX_MESSAGE_CHARS",
    "SLACK_SIGNATURE_HEADER",
    "SLACK_TIMESTAMP_HEADER",
    "InboundFlow",
    "InboundIgnore",
    "InboundNonText",
    "InboundText",
    "NormalisedEvent",
    "OAuthIdentityResolver",
    "SlackClient",
    "SlackConnector",
    "SlackLinkingService",
    "SlackNonTextKind",
    "SlackOAuthClient",
    "SlackSocketClient",
    "SlackSocketConnection",
    "build_ack",
    "build_authorize_url",
    "build_events_app",
    "build_slack_app",
    "classify_event",
    "decline_message",
    "interpret_envelope",
    "render_outbound",
    "verify_slack_signature",
]

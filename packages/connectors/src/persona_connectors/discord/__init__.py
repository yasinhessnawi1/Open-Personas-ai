"""The Discord connector adapter (Spec C3) — a thin DM adapter on the C1 framework.

A deliberately **thin** adapter implementing C1's ``Connector`` for Discord: it
converts Discord gateway ``MESSAGE_CREATE`` events to C1's ``NormalisedInbound`` (DM
only — D-C3-5), lets the **shared** inbound flow drive the reply
(:class:`~persona_connectors.domain.flow.SharedInboundFlow`), and renders C1's
``NormalisedOutbound`` back as Discord Markdown messages — plus Discord's OAuth
account-linking carrier and its persistent-gateway transport. Everything else —
routing, persona selection, the conversation model, identity mapping, C0 delivery —
is C1's and is *used*, not reimplemented.

The whole adapter is **api-free** (it depends only on C1's owned-surface ports +
persona-core contracts + ``httpx``/``websockets``); the api-coupling lives in
:mod:`persona_connectors.composition` (the reversibility guarantee, C1-D-1). The
Discord REST API is plain JSON-over-HTTPS, so the client talks to it with ``httpx``
directly; the gateway is a WebSocket over ``websockets`` (D-C3-X-no-new-dep — no
``discord.py``).
"""

from __future__ import annotations

from persona_connectors.discord.app import build_discord_app
from persona_connectors.discord.client import DISCORD_MAX_MESSAGE_CHARS, DiscordClient
from persona_connectors.discord.connector import DISCORD_CAPABILITIES, DiscordConnector
from persona_connectors.discord.flow import InboundFlow
from persona_connectors.discord.gateway import (
    INTENTS_DIRECT_MESSAGES,
    DiscordGateway,
    GatewayConnection,
)
from persona_connectors.discord.inbound import (
    PLATFORM,
    DiscordNonTextKind,
    InboundIgnore,
    InboundNonText,
    InboundText,
    NormalisedUpdate,
    classify_message,
)
from persona_connectors.discord.linking import (
    DiscordLinkingService,
    DiscordOAuthClient,
    OAuthIdentityResolver,
    build_authorize_url,
)
from persona_connectors.discord.non_text import decline_message
from persona_connectors.discord.render import render_outbound

__all__ = [
    "DISCORD_CAPABILITIES",
    "DISCORD_MAX_MESSAGE_CHARS",
    "INTENTS_DIRECT_MESSAGES",
    "PLATFORM",
    "DiscordClient",
    "DiscordConnector",
    "DiscordGateway",
    "DiscordLinkingService",
    "DiscordNonTextKind",
    "DiscordOAuthClient",
    "GatewayConnection",
    "InboundFlow",
    "InboundIgnore",
    "InboundNonText",
    "InboundText",
    "NormalisedUpdate",
    "OAuthIdentityResolver",
    "build_authorize_url",
    "build_discord_app",
    "classify_message",
    "decline_message",
    "render_outbound",
]

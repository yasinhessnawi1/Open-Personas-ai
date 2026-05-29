"""Response models for the hosted API (spec 08, T06).

Pydantic v2 models that shape the JSON the API returns + the SSE event payloads.
Clean and explicit so FastAPI's OpenAPI spec (the web app's TS-client source,
spec 09) is well-formed — optional fields are properly nullable, the SSE
payloads serialise via ``model_dump_json`` straight into ``data:`` lines.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — Pydantic needs it at runtime

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ChunkEvent",
    "ConversationDetail",
    "ConversationSummary",
    "CreditsResponse",
    "DoneEvent",
    "MessageView",
    "PersonaDetail",
    "PersonaSummary",
    "RunStatusResponse",
    "ToolCallEvent",
    "ToolResultEvent",
    "ToolSummary",
    "UsageEntry",
]


class _Output(BaseModel):
    """Base for responses: reject unknown fields so we never leak stray data."""

    model_config = ConfigDict(extra="forbid")


# -- personas ---------------------------------------------------------------


class PersonaSummary(_Output):
    """A persona in a list view (no full YAML)."""

    id: str
    name: str
    role: str
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime


class PersonaDetail(_Output):
    """A persona's full detail (YAML + metadata)."""

    id: str
    yaml: str
    schema_version: str
    avatar_url: str | None = None
    created_at: datetime
    updated_at: datetime


# -- conversations ----------------------------------------------------------


class ConversationSummary(_Output):
    """A conversation in a list view."""

    id: str
    persona_id: str
    title: str
    created_at: datetime
    updated_at: datetime


class MessageView(_Output):
    """A single message in a conversation history."""

    id: str
    role: str
    content: str
    created_at: datetime
    # Opaque connector passthrough (D-08-3); null for web-UI messages.
    channel: dict[str, object] | None = None


class ConversationDetail(_Output):
    """Full conversation history."""

    id: str
    persona_id: str
    title: str
    messages: list[MessageView]
    created_at: datetime
    updated_at: datetime


# -- SSE chat events (§5.2) -------------------------------------------------


class ChunkEvent(_Output):
    """``event: chunk`` — an incremental delta of the assistant's response."""

    delta: str
    is_final: bool = False


class ToolCallEvent(_Output):
    """``event: tool_call`` — the model invoked a tool."""

    tool: str
    args: dict[str, object] = Field(default_factory=dict)


class ToolResultEvent(_Output):
    """``event: tool_result`` — a tool's result (D-03-3: is_error + content)."""

    tool: str
    content: str
    is_error: bool = False


class DoneEvent(_Output):
    """``event: done`` — the terminal event.

    ``format_hints`` (D-08-3) is the connector echo channel: empty ``{}`` from
    the API; connectors populate/interpret it themselves (spec 12).
    """

    usage: dict[str, int] = Field(default_factory=dict)
    tier: str
    format_hints: dict[str, str] = Field(default_factory=dict)


# -- runs (§5.3) ------------------------------------------------------------


class RunStatusResponse(_Output):
    """A run's status + its accumulated steps (JSON-serialised Run/Step)."""

    id: str
    persona_id: str
    task: str
    status: str
    steps: list[dict[str, object]] = Field(default_factory=list)
    output: str | None = None
    error: str | None = None


# -- credits / usage (§5.5) -------------------------------------------------


class CreditsResponse(_Output):
    """The user's current credit balance (stub counter)."""

    balance: int


class UsageEntry(_Output):
    """One usage-log row (per-turn telemetry, paginated)."""

    persona_id: str | None = None
    tier_used: str
    model_name: str
    prompt_tokens: int
    completion_tokens: int
    cost_cents: float
    created_at: datetime


# -- tools / skills (§5.4) --------------------------------------------------


class ToolSummary(_Output):
    """A tool or skill name + description (read-only listing)."""

    name: str
    description: str

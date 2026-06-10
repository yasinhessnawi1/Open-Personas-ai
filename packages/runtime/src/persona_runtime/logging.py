"""Per-turn telemetry — TurnLog, the writer port, and cost estimation (T06).

Every completed turn produces one :class:`TurnLog` (spec §7) recording the tier,
model, token usage, latency, estimated cost, tool-call count, skill used, and
whether history compaction fired. The log is written through a
:class:`TurnLogWriter` port: :class:`JSONLTurnLogWriter` for the CLI/local path,
:class:`MemoryTurnLogWriter` for tests. The hosted service (spec 08) implements
the same port against the Postgres ``turn_logs`` table.

`TurnLog` is a frozen **Pydantic** model, not a ``@dataclass`` (D-05-9): it
crosses the API/Postgres boundary and needs ``model_dump_json`` + tz-aware
datetime validation, following the D-02-2 / D-03-3 precedent.

Cost (D-05-10, S05-3) is an *estimate* from a hand-maintained price table — not
a billing record. Unknown ``(provider, model)`` pairs cost ``0.0`` and log a
warning. **Prices are illustrative v0.1 placeholders; verify against provider
pricing pages before any billing use.**
"""

from __future__ import annotations

import threading
from datetime import datetime  # noqa: TC003 — Pydantic needs runtime access for TurnLog.timestamp
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from persona.logging import get_logger
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from persona_runtime.routing import (
    RoutingDecision,  # noqa: TC001 — Pydantic model field needs runtime reference
)

if TYPE_CHECKING:
    from pathlib import Path

__all__ = [
    "JSONLTurnLogWriter",
    "MemoryTurnLogWriter",
    "TurnLog",
    "TurnLogWriter",
    "estimate_cost_cents",
]

_logger = get_logger("runtime.turnlog")


class TurnLog(BaseModel):
    """Telemetry for one completed turn (spec §7).

    Frozen + ``extra="forbid"``. ``timestamp`` must be tz-aware (UTC), matching
    the spec-01 model convention.

    Spec 18 (T12; D-18-X-turnlog-extension) extends the shape additively with
    routing observability:

    * :attr:`routing_decision` — the full :class:`RoutingDecision` from
      :meth:`Router.route`; serialises as nested JSON when persisted.
    * :attr:`routing_latency_ms` — wall-clock duration of the router's
      decision (from :func:`time.perf_counter` around the :meth:`route`
      call). Distinct from :attr:`latency_ms` which covers the whole turn.
    * :attr:`routing_fallback_triggered` — whether the :class:`UnifiedRouter`
      smart path fell back to the embedded :class:`HeuristicRouter`.
    * :attr:`routing_fallback_reason` — one of ``"timeout"`` /
      ``"scoring_error"`` / ``"empty_metadata"`` / ``"partial_metadata:<tier>"``
      when ``routing_fallback_triggered`` is ``True`` (D-18-X-fallback-instrumentation).

    All four routing fields are OPTIONAL — pre-Spec-18 callers (legacy tests
    that construct TurnLog directly without routing data) stay green by
    omitting them.

    Spec 20 (T12; D-20-5) extends the shape additively with content-hash-only
    reasoning observability:

    * :attr:`reasoning_total_tokens` — count of tokens spent on reasoning
      content during this turn (provider-reported when available; otherwise
      ``None``). Distinct from :attr:`completion_tokens` which excludes the
      reasoning trace for providers that account separately.
    * :attr:`reasoning_text_hash` — sha256 hex digest of the concatenated
      reasoning text emitted by the stream. NEVER persist the raw text
      (content-hash-only per the D-15-X-hard-line-filter precedent —
      reasoning may contain PII or jailbreak attempts the prompt builder
      filtered out). ``None`` if the provider emitted no reasoning.

    Both reasoning fields are OPTIONAL and default to ``None``; pre-Spec-20
    callers stay green by omitting them.

    Spec 20 (T19; D-20-9) extends the shape additively with multi-model
    fallback instrumentation. Operators consume these via the JSONL TurnLog
    stream to identify fallback-rate hot-spots; MAINTENANCE.md D-20-7 row
    triggers operator investigation when fallback-rate > N% / 7-day window.

    * :attr:`tier_model_chosen` — the actual model that successfully returned
      (``None`` when the wrapper exhausted all backends with
      :class:`AllModelsFailedError`).
    * :attr:`tier_provider_used` — provider whose backend served the turn
      (e.g. ``"nvidia"`` / ``"anthropic"``). ``None`` when
      ``AllModelsFailedError`` surfaced.
    * :attr:`tier_fallback_count` — how many backends attempted before
      success. ``0`` means primary served cleanly. Equal-length invariant
      with the reasons / providers lists.
    * :attr:`tier_fallback_reasons` — per-fallback error class name (e.g.
      ``"RateLimitError"``, ``"BackendTimeoutError"``,
      ``"ProviderCredentialMissingError"``). **Class names ONLY**, never
      error message text or context dict values (mirror the
      D-15-X-hard-line-filter content-hash-only-audit privacy precedent).
    * :attr:`tier_fallback_providers` — per-fallback provider name
      (operator-visible signal for cross-provider routing patterns).
      Index ``i`` describes the same fallback attempt as
      ``tier_fallback_reasons[i]``.
    * :attr:`fallback_engaged` — derived operator-convenience: ``True`` iff
      ``tier_fallback_count > 0``. Explicit field (NOT Pydantic
      ``computed_field``) so it serialises cleanly to JSONL and dashboards
      can aggregate without computing.

    All six fallback fields are OPTIONAL; pre-Spec-20 callers stay green
    by omitting them. The :meth:`_validate_fallback_invariants` after-
    validator enforces (a) length-match between count + reasons + providers
    and (b) ``fallback_engaged == (tier_fallback_count > 0)``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    conversation_id: str
    turn_index: int = Field(ge=0)
    tier_used: str
    model_name: str
    provider: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    cost_cents: float = Field(ge=0.0)
    tool_calls: int = Field(default=0, ge=0)
    skill_used: str | None = None
    history_compacted: bool = False
    timestamp: datetime
    routing_decision: RoutingDecision | None = None
    routing_latency_ms: float = Field(default=0.0, ge=0.0)
    routing_fallback_triggered: bool = False
    routing_fallback_reason: str | None = None
    # Spec 20 T12 (D-20-5): content-hash-only reasoning observability.
    reasoning_total_tokens: int | None = Field(default=None, ge=0)
    reasoning_text_hash: str | None = None
    # Spec 20 T19 (D-20-9) — multi-model fallback instrumentation. Additive
    # per D-05-9. Operators consume these via the JSONL TurnLog stream;
    # MAINTENANCE.md D-20-7 row triggers operator investigation when the
    # fallback-rate metric exceeds N% over a 7-day window. Class-name-only
    # privacy discipline mirrors D-15-X-hard-line-filter.
    tier_model_chosen: str | None = None
    tier_provider_used: str | None = None
    tier_fallback_count: int = Field(default=0, ge=0)
    tier_fallback_reasons: list[str] = Field(default_factory=list)
    tier_fallback_providers: list[str] = Field(default_factory=list)
    fallback_engaged: bool = False

    @field_validator("timestamp", mode="after")
    @classmethod
    def _timestamp_must_be_tz_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            msg = "naive datetime not allowed on TurnLog.timestamp"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _validate_fallback_invariants(self) -> TurnLog:
        """Enforce the two T19 D-20-9 invariants on the fallback fields.

        1. ``len(tier_fallback_reasons) == len(tier_fallback_providers) ==
           tier_fallback_count`` — every counted fallback has a matching
           class-name + provider pair, with consistent index ordering.
        2. ``fallback_engaged == (tier_fallback_count > 0)`` — the derived
           bool is not allowed to drift from the count.
        """
        if (
            len(self.tier_fallback_reasons) != self.tier_fallback_count
            or len(self.tier_fallback_providers) != self.tier_fallback_count
        ):
            msg = (
                "tier_fallback_count must equal len(tier_fallback_reasons) and "
                f"len(tier_fallback_providers); got count={self.tier_fallback_count}, "
                f"reasons={len(self.tier_fallback_reasons)}, "
                f"providers={len(self.tier_fallback_providers)}"
            )
            raise ValueError(msg)
        if self.fallback_engaged != (self.tier_fallback_count > 0):
            msg = (
                "fallback_engaged must equal (tier_fallback_count > 0); "
                f"got fallback_engaged={self.fallback_engaged}, "
                f"tier_fallback_count={self.tier_fallback_count}"
            )
            raise ValueError(msg)
        return self


@runtime_checkable
class TurnLogWriter(Protocol):
    """Port for persisting a :class:`TurnLog`. Write-only (CQS)."""

    def write(self, log: TurnLog) -> None:
        """Persist one turn log. No return value (CQS)."""
        ...


class JSONLTurnLogWriter:
    """Appends one JSON object per turn to ``<root>/<conversation_id>.jsonl``.

    Mirrors the spec-01 audit-log path convention (D-01-6 / D-05-10): co-located
    with the data, env-overridable via ``PERSONA_TURNLOG_PATH``. Single-process
    safe via a lock; the line-append itself is atomic enough at persona scale.
    Hosted multi-process safety lands with the Postgres writer in spec 08.
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        self._lock = threading.Lock()

    def write(self, log: TurnLog) -> None:
        """Append ``log`` as one JSON line under the conversation's file."""
        self._root.mkdir(parents=True, exist_ok=True)
        payload = log.model_dump_json()
        path = self._root / f"{log.conversation_id}.jsonl"
        with self._lock, path.open("a", encoding="utf-8") as f:
            f.write(payload)
            f.write("\n")


class MemoryTurnLogWriter:
    """In-memory writer for tests (mirrors spec-03's MemoryToolAuditLogger)."""

    def __init__(self) -> None:
        self.logs: list[TurnLog] = []

    def write(self, log: TurnLog) -> None:
        """Record ``log`` in insertion order."""
        self.logs.append(log)


# Hand-maintained estimate (S05-3 / D-05-10): (provider, model) ->
# (prompt_cents_per_1k_tokens, completion_cents_per_1k_tokens).
# v0.1 PLACEHOLDERS — verify against provider pricing before any billing use.
_PRICE_TABLE: dict[tuple[str, str], tuple[float, float]] = {
    ("anthropic", "claude-sonnet-4-6"): (0.30, 1.50),
    ("anthropic", "claude-haiku-4-5"): (0.08, 0.40),
    ("deepseek", "deepseek-chat"): (0.014, 0.028),
    ("groq", "llama-3.1-8b-instant"): (0.005, 0.008),
}

_warned_unknown: set[tuple[str, str]] = set()


def estimate_cost_cents(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
) -> float:
    """Estimate the turn cost in cents from the price table (S05-3).

    Returns ``0.0`` for an unknown ``(provider, model)`` pair and logs a warning
    once per unknown pair. This is an estimate for telemetry, not a billing
    record.
    """
    key = (provider, model)
    prices = _PRICE_TABLE.get(key)
    if prices is None:
        if key not in _warned_unknown:
            _warned_unknown.add(key)
            _logger.warning(
                "no price-table entry; cost estimated as 0 provider={provider} model={model}",
                provider=provider,
                model=model,
            )
        return 0.0
    prompt_price, completion_price = prices
    return (prompt_tokens / 1000.0) * prompt_price + (completion_tokens / 1000.0) * completion_price

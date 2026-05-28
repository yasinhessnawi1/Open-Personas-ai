"""Persona runtime — conversation loop, router, and agentic engine.

The public surface spec 06 (agentic loop) and spec 08 (API) import:

- :class:`ConversationLoop` — orchestrates one turn (the keystone).
- :class:`PromptBuilder` + :class:`RetrievedContext` — prompt assembly.
- :class:`Router` — rule-based tier selection.
- :class:`TierConfig` / :class:`TierRegistry` / :func:`tier_registry_from_env`
  — tier configuration and the lazily-cached backend registry.
- :class:`TurnLog` / :class:`TurnLogWriter` / :class:`JSONLTurnLogWriter` /
  :class:`MemoryTurnLogWriter` — per-turn telemetry.
- :exc:`TierNotConfiguredError` — the one runtime domain exception (D-05-2).
"""

from __future__ import annotations

from persona_runtime.errors import TierNotConfiguredError
from persona_runtime.logging import (
    JSONLTurnLogWriter,
    MemoryTurnLogWriter,
    TurnLog,
    TurnLogWriter,
)
from persona_runtime.loop import ConversationLoop
from persona_runtime.prompt import PromptBuilder, RetrievedContext
from persona_runtime.router import Router
from persona_runtime.tier import TierConfig, TierRegistry, tier_registry_from_env

__all__ = [
    "ConversationLoop",
    "JSONLTurnLogWriter",
    "MemoryTurnLogWriter",
    "PromptBuilder",
    "RetrievedContext",
    "Router",
    "TierConfig",
    "TierNotConfiguredError",
    "TierRegistry",
    "TurnLog",
    "TurnLogWriter",
    "tier_registry_from_env",
]

"""Runtime composition root (spec 08, T10).

Builds the **real** ``ConversationLoop`` / ``AgenticLoop`` per request, wiring
every collaborator (the keystones T08/T11 consume a ``build_*`` closure from
here). The app-scoped ``TierRegistry`` + MCP clients are owned by the lifespan
(T10 startup/shutdown): ``await tier_registry.aclose()`` + ``await
client.disconnect()`` on shutdown (D-05-4 / spec-06 handoff). The loops never
close the registry.

Per request, the four typed stores compose ``PostgresBackend`` over the
**RLS engine** (the checkout listener scopes every store connection to the
tenant — D-08-1), so the loop's memory reads/writes are tenant-isolated.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.audit import JSONLAuditLogger
from persona.config import PersonaCoreConfig
from persona.errors import PersonaNotFoundError
from persona.history import ConversationHistoryManager
from persona.schema.persona import Persona
from persona.skills import SkillInjector, SkillScanner, make_use_skill_tool
from persona.stores import (
    EpisodicStore,
    IdentityStore,
    SelfFactsStore,
    WorldviewStore,
)
from persona.stores.postgres import PostgresBackend
from persona.tools import build_default_toolbox
from persona_runtime.agentic.loop import AgenticLoop
from persona_runtime.loop import ConversationLoop
from persona_runtime.prompt import PromptBuilder
from persona_runtime.router import Router
from sqlalchemy import select

from persona_api.db.models import personas as personas_t

if TYPE_CHECKING:
    from pathlib import Path

    from persona.stores.embedder import Embedder
    from persona.stores.protocol import MemoryStore
    from persona.tools.mcp.client import MCPClient
    from persona_runtime.logging import TurnLogWriter
    from persona_runtime.tier import TierRegistry
    from sqlalchemy import Engine

__all__ = ["RuntimeFactory"]


class RuntimeFactory:
    """Composes per-request loops; owns the app-scoped registry + MCP clients.

    One instance lives on ``app.state`` for the process. ``build_conversation_loop``
    / ``build_agentic_loop`` are the closures the routes call per request (the
    persona is loaded + stores built under the active RLS scope).
    """

    def __init__(
        self,
        *,
        rls_engine: Engine,
        embedder: Embedder,
        tier_registry: TierRegistry,
        turn_log_writer: TurnLogWriter,
        audit_root: Path,
        core_config: PersonaCoreConfig | None = None,
    ) -> None:
        self._engine = rls_engine
        self._embedder = embedder
        self._tier_registry = tier_registry
        self._turn_log_writer = turn_log_writer
        self._audit_root = audit_root
        self._core_config = core_config or PersonaCoreConfig()
        # MCP clients accumulated across requests, closed on shutdown.
        self._mcp_clients: list[MCPClient] = []

    # -- shared per-request pieces ------------------------------------------

    def _load_persona(self, persona_id: str) -> Persona:
        """Load + validate the persona's YAML from the RLS-scoped row (→ 404)."""
        with self._engine.begin() as conn:
            row = (
                conn.execute(select(personas_t.c.yaml).where(personas_t.c.id == persona_id))
                .mappings()
                .first()
            )
        if row is None:
            raise PersonaNotFoundError("persona not found", context={"id": persona_id})
        import yaml

        raw = yaml.safe_load(str(row["yaml"]))
        if isinstance(raw, dict):
            raw["persona_id"] = persona_id
        return Persona.model_validate(raw)

    def _build_stores(self) -> dict[str, MemoryStore]:
        """The four typed stores over PostgresBackend (RLS-scoped engine)."""
        backend = PostgresBackend(engine=self._engine, embedder=self._embedder)
        audit = JSONLAuditLogger(self._audit_root)
        return {
            "identity": IdentityStore(backend=backend, audit_logger=audit),
            "self_facts": SelfFactsStore(backend=backend, audit_logger=audit),
            "worldview": WorldviewStore(backend=backend, audit_logger=audit),
            "episodic": EpisodicStore(backend=backend, audit_logger=audit),
        }

    async def _build_toolbox(self, persona: Persona, scanned_skills: list[object]) -> object:
        """Build the toolbox (+ use_skill when the persona has skills). MCP
        clients are tracked for shutdown."""
        extra = [make_use_skill_tool(scanned_skills)] if scanned_skills else None  # type: ignore[arg-type]
        toolbox, mcp_clients = await build_default_toolbox(
            self._core_config, persona, extra_tools=extra
        )
        self._mcp_clients.extend(mcp_clients)
        return toolbox

    def _scan_skills(self, persona: Persona) -> tuple[SkillScanner, list[object]]:
        scanner = SkillScanner(skill_paths=[])  # built-in skill discovery via config later
        scanned = scanner.scan(
            declared_skills=persona.skills,
            tool_allow_list=list(persona.tools) if persona.tools else None,
        )
        return scanner, list(scanned)

    # -- the closures the routes call ---------------------------------------

    async def build_conversation_loop(self, persona_id: str) -> ConversationLoop:
        """Construct the ConversationLoop for ``persona_id`` (KEYSTONE 1, T08)."""
        persona = self._load_persona(persona_id)
        scanner, scanned = self._scan_skills(persona)
        toolbox = await self._build_toolbox(persona, scanned)
        return ConversationLoop(
            persona=persona,
            stores=self._build_stores(),
            toolbox=toolbox,  # type: ignore[arg-type]
            skill_scanner=scanner,
            skill_injector=SkillInjector(),
            scanned_skills=scanned,  # type: ignore[arg-type]
            history_manager=ConversationHistoryManager(),
            prompt_builder=PromptBuilder(),
            router=Router(),
            tier_registry=self._tier_registry,
            turn_log_writer=self._turn_log_writer,
        )

    async def build_agentic_loop(self, persona_id: str) -> AgenticLoop:
        """Construct the AgenticLoop for ``persona_id`` (KEYSTONE 2, T11)."""
        persona = self._load_persona(persona_id)
        _scanner, scanned = self._scan_skills(persona)
        toolbox = await self._build_toolbox(persona, scanned)
        return AgenticLoop(
            persona=persona,
            stores=self._build_stores(),
            toolbox=toolbox,  # type: ignore[arg-type]
            skill_injector=SkillInjector(),
            scanned_skills=scanned,  # type: ignore[arg-type]
            prompt_builder=PromptBuilder(),
            router=Router(),
            tier_registry=self._tier_registry,
        )

    async def build_title(self, first_message: str) -> str:
        """Generate a short (≤5-word) conversation title from the first message,
        using the **small** tier (pure boilerplate — architecture §5.1.1). Returns
        the title text; the caller (chat_service) applies it best-effort."""
        from datetime import UTC, datetime

        from persona.schema.conversation import ConversationMessage

        backend = self._tier_registry.get("small")
        now = datetime.now(UTC)
        prompt = [
            ConversationMessage(
                role="system",
                content=(
                    "Summarise the user's message as a conversation title of at most "
                    "5 words. Output ONLY the title — no quotes, no punctuation, no prose."
                ),
                created_at=now,
            ),
            ConversationMessage(role="user", content=first_message, created_at=now),
        ]
        response = await backend.chat(prompt, temperature=0.0, max_tokens=24)
        return response.content.strip().strip('"').splitlines()[0] if response.content else ""

    # -- lifecycle ----------------------------------------------------------

    async def aclose(self) -> None:
        """Shutdown: close the tier registry + every MCP client (D-05-4)."""
        await self._tier_registry.aclose()
        for client in self._mcp_clients:
            await client.disconnect()

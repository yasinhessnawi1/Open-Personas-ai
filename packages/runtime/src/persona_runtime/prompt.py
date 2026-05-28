"""The prompt builder (T05; D-05-6, D-05-7, D-05-8).

Assembles the model-ready prompt as a ``list[ConversationMessage]``: one system
message (identity → constraints → self-facts → worldview → episodic → skill
index → active skill content → footer, per spec §5.1), then the compacted +
recent history, then the current user message.

Two budgets, kept distinct:

- The **skill content** budget (2000 tokens) is owned and enforced by
  :class:`persona.skills.SkillInjector` (D-04-7). The builder receives
  already-budgeted ``matched_skill_content`` and splices it verbatim — it does
  NOT define ``SKILL_TOKEN_BUDGET`` and does NOT re-enforce (D-05-7).
- The **whole-prompt** budget is the backend's context window (``max_tokens``).
  When the assembled prompt would exceed it, retrieved context is dropped in
  order — episodic → worldview → self-facts (lowest-relevance first) — and then
  history is truncated more aggressively. Identity, constraints, and the skill
  index are the persona floor and are never dropped (spec §5.3).

Token estimation uses ``persona.skills.count_tokens`` (the shared
``cl100k_base`` encoder, D-05-8) — an *estimate* for budgeting. The exact token
counts in :class:`persona_runtime.logging.TurnLog` come from the backend's
``usage`` field, post-call. Don't conflate the two.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from persona.schema.chunks import PersonaChunk  # noqa: TC002 — Pydantic needs runtime ref
from persona.schema.conversation import ConversationMessage
from persona.skills import count_tokens
from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from persona.schema.persona import Persona

__all__ = ["PromptBuilder", "RetrievedContext"]

_FOOTER = "Stay in character. Cite sources when using tool results."


class RetrievedContext(BaseModel):
    """The per-turn retrieval the loop fills from the stores (D-05-6).

    A frozen bundle so the :class:`PromptBuilder` can be tested without a live
    store. ``identity`` comes from ``identity.get_all(persona_id)``; the other
    three from ``query(persona_id, message, top_k=3)``.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    identity: list[PersonaChunk] = Field(default_factory=list)
    self_facts: list[PersonaChunk] = Field(default_factory=list)
    worldview: list[PersonaChunk] = Field(default_factory=list)
    episodic: list[PersonaChunk] = Field(default_factory=list)


class PromptBuilder:
    """Assembles the system prompt + history + user message (spec §5)."""

    def build(
        self,
        persona: Persona,
        context: RetrievedContext,
        history: list[ConversationMessage],
        skill_index: str,
        user_message: str,
        *,
        max_tokens: int,
        matched_skill_content: str | None = None,
    ) -> list[ConversationMessage]:
        """Build the full prompt as a message list.

        Args:
            persona: The active persona (identity + constraints come from here,
                always — never truncated).
            context: The retrieved self-facts / worldview / episodic chunks.
            history: Compacted summary + recent verbatim turns (from the history
                manager). Does NOT include the current user message.
            skill_index: The rendered "available skills" block (may be empty).
            user_message: The current turn's user message — appended last.
            max_tokens: The backend's context-window budget. The assembled
                prompt is reduced (retrieved context dropped, then history
                truncated) to fit.
            matched_skill_content: Already-budgeted active-skill content from
                the injector (D-05-7). ``None`` when no skill is active.

        Returns:
            ``[system_message, *history, user_message]`` — sized to ``max_tokens``.
        """
        reduced_context = context
        trimmed_history = list(history)

        # Build once, then reduce only if over budget (the common case fits).
        messages = self._assemble(
            persona,
            reduced_context,
            trimmed_history,
            skill_index,
            user_message,
            matched_skill_content,
        )
        if self._token_total(messages) <= max_tokens:
            return messages

        # Over budget: drop retrieved context episodic → worldview → self-facts.
        for dropped in self._reductions(reduced_context):
            reduced_context = dropped
            messages = self._assemble(
                persona,
                reduced_context,
                trimmed_history,
                skill_index,
                user_message,
                matched_skill_content,
            )
            if self._token_total(messages) <= max_tokens:
                return messages

        # Still over after zeroing retrieved context: truncate history harder
        # (drop oldest verbatim turns; keep the most recent).
        while trimmed_history and self._token_total(messages) > max_tokens:
            trimmed_history = trimmed_history[1:]
            messages = self._assemble(
                persona,
                reduced_context,
                trimmed_history,
                skill_index,
                user_message,
                matched_skill_content,
            )
        return messages

    def _assemble(
        self,
        persona: Persona,
        context: RetrievedContext,
        history: list[ConversationMessage],
        skill_index: str,
        user_message: str,
        matched_skill_content: str | None,
    ) -> list[ConversationMessage]:
        """Compose the message list in the spec §5.1 order."""
        system_text = self._render_system(persona, context, skill_index, matched_skill_content)
        now = datetime.now(UTC)
        system = ConversationMessage(role="system", content=system_text, created_at=now)
        user = ConversationMessage(role="user", content=user_message, created_at=now)
        return [system, *history, user]

    def _render_system(
        self,
        persona: Persona,
        context: RetrievedContext,
        skill_index: str,
        matched_skill_content: str | None,
    ) -> str:
        """Render the system block in the spec §5.1 ordering."""
        parts: list[str] = []

        # 1. Identity opener.
        ident = persona.identity
        parts.append(f"You are {ident.name}, {ident.role}.\n{ident.background}".rstrip())

        # 2. Constraints ("You must NOT:" numbered list).
        if ident.constraints:
            lines = ["You must NOT:"]
            lines += [f"{i}. {c}" for i, c in enumerate(ident.constraints, start=1)]
            parts.append("\n".join(lines))

        # 3. Self-facts.
        if context.self_facts:
            lines = ["Relevant facts about yourself:"]
            lines += [f"- {c.text}" for c in context.self_facts]
            parts.append("\n".join(lines))

        # 4. Worldview (epistemic tags in parentheses).
        if context.worldview:
            lines = ["Your views:"]
            for c in context.worldview:
                tag = c.metadata.get("epistemic")
                suffix = f" ({tag})" if tag else ""
                lines.append(f"- {c.text}{suffix}")
            parts.append("\n".join(lines))

        # 5. Episodic.
        if context.episodic:
            lines = ["From earlier conversations:"]
            lines += [f"- {c.text}" for c in context.episodic]
            parts.append("\n".join(lines))

        # 6. Skill index (already rendered; empty string when no skills).
        if skill_index:
            parts.append(skill_index)

        # 7. Active skill content (already budget-sized by the injector).
        if matched_skill_content:
            parts.append(matched_skill_content)

        # 8. Footer.
        parts.append(_FOOTER)

        return "\n\n".join(parts)

    @staticmethod
    def _reductions(context: RetrievedContext) -> list[RetrievedContext]:
        """Progressively-reduced contexts: drop episodic, then worldview, then self-facts.

        v0.1 reduction granularity is whole-store (spec §5.3): episodic → also
        worldview → also self-facts cleared. Partial per-chunk dropping by
        relevance (``distance``) is a future refinement; the whole-store ladder
        is enough to keep long conversations within the window.
        """
        stages: list[RetrievedContext] = []
        # Stage 1: drop episodic.
        stages.append(context.model_copy(update={"episodic": []}))
        # Stage 2: also drop worldview.
        stages.append(context.model_copy(update={"episodic": [], "worldview": []}))
        # Stage 3: also drop self-facts (all retrieved context gone).
        stages.append(
            context.model_copy(update={"episodic": [], "worldview": [], "self_facts": []})
        )
        return stages

    @staticmethod
    def _token_total(messages: list[ConversationMessage]) -> int:
        """Estimate the prompt's token count via the shared cl100k_base encoder."""
        return sum(count_tokens(m.content) for m in messages)

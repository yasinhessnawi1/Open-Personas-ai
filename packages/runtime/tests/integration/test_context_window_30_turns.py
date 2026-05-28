"""Acceptance #12 — a 30-turn conversation stays within an 8K mid-tier window.

Per Phase 1 steer #7: construct a 30-turn ``Conversation`` directly and assert
the rendered prompt token count is ``< 8000`` after ``history_manager.manage()``
+ ``prompt_builder.build()``. No 30 mock round-trips — this exercises the budget
logic, not the loop's streaming.

This duplicates the unit-level check in ``test_prompt.py`` at the integration
mark so the acceptance criterion is verifiable in the integration suite too,
with the bundled built-in skill index in the prompt (a realistic load).
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from persona.history import ConversationHistoryManager
from persona.schema.chunks import PersonaChunk
from persona.schema.conversation import Conversation, ConversationMessage
from persona.schema.persona import Persona, PersonaIdentity
from persona.skills import SkillScanner, count_tokens, render_skill_index
from persona_runtime.prompt import PromptBuilder, RetrievedContext

pytestmark = pytest.mark.integration

_BUILTIN_ROOT = Path(__import__("persona").__file__).parent / "skills" / "builtin"


def _chunk(text: str, *, meta: dict[str, str] | None = None) -> PersonaChunk:
    return PersonaChunk(
        id=f"id-{abs(hash(text)) % 100000}",
        text=text,
        metadata=meta or {},
        created_at=datetime.now(UTC),
    )


def test_30_turn_prompt_under_8000_tokens_with_real_skill_index() -> None:
    persona = Persona(
        persona_id="astrid",
        identity=PersonaIdentity(
            name="Astrid",
            role="Norwegian tenancy law assistant",
            background="Knows husleieloven.",
            constraints=["Never give binding legal advice."],
        ),
        skills=["web_research", "document_drafting"],
    )
    # Real skill index from the bundled built-ins (a realistic prompt load).
    scanner = SkillScanner([_BUILTIN_ROOT])
    scanned = scanner.scan(persona.skills)
    skill_index = render_skill_index(scanned)

    manager = ConversationHistoryManager(compact_every=10, keep_recent=5)
    messages = [
        ConversationMessage(
            role="user" if i % 2 == 0 else "assistant",
            content=(
                f"Turn {i}: a realistic message about Norwegian tenancy law, deposits, "
                f"mould complaints, and dispute resolution via Husleietvistutvalget."
            ),
            created_at=datetime.now(UTC),
        )
        for i in range(30)
    ]
    conv = Conversation(conversation_id="c30", persona_id="astrid", messages=messages)
    history = manager.manage(
        conv, summariser=lambda _m: "Earlier: discussed deposits, mould, and ODR options."
    )

    ctx = RetrievedContext(
        self_facts=[_chunk("I specialise in husleieloven.")],
        worldview=[_chunk("Tenants have strong protections.", meta={"epistemic": "fact"})],
        episodic=[_chunk("Earlier we discussed a mould complaint.")],
    )
    prompt = PromptBuilder().build(
        persona,
        ctx,
        history,
        skill_index,
        "So what should I do about my deposit?",
        max_tokens=8000,
    )
    total = sum(count_tokens(m.content) for m in prompt)
    assert total < 8000, f"30-turn prompt was {total} tokens (expected < 8000)"

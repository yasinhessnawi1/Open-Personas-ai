"""The consent gate + the injection audit (S1 T4, S1-D-6/D-7).

T4 is the enforcement + audit seam. It proves:

- the enable-time consent gate refuses an above-threshold skill without granted
  consent (default DENY-unvetted) — not injected, persona unaffected (criterion 3);
- ``builtin`` / ``vetted`` skills never consult the gate (criterion 5: trusted
  content activates freely);
- exactly ONE ``AuditEvent`` per injection (``SKILL_INJECTED``) and per consent
  refusal (``SKILL_REFUSED``), reusing the existing ``AuditLogger`` — provenance +
  consent_state in ``metadata``, the ``"skill"`` store sentinel;
- the audit is INERT — emitting it (or having no sink) never perturbs the guard
  output or the injection path.

Both the chat ``ConversationLoop`` and the agentic ``AgenticLoop`` are covered.
"""

# ruff: noqa: SLF001 — reaches into _compose_skill / _maybe_inject_skill.

from __future__ import annotations

from pathlib import Path

import pytest
from _fakes import FakeStore, ScriptedBackend  # type: ignore[import-not-found]
from persona.audit import AuditAction, MemoryAuditLogger
from persona.backends import BackendConfig
from persona.history import ConversationHistoryManager
from persona.schema.persona import Persona, PersonaIdentity
from persona.schema.skills import SkillProvenance, SkillSpec, SkillTrust
from persona.schema.tools import ToolCall, ToolResult
from persona.skills import SkillInjector, SkillScanner, count_tokens
from persona.skills.composition import SkillCompositionState
from persona.tools import Toolbox
from persona_runtime.agentic.loop import AgenticLoop
from persona_runtime.logging import MemoryTurnLogWriter
from persona_runtime.loop import ConversationLoop
from persona_runtime.prompt import PromptBuilder
from persona_runtime.router import Router
from persona_runtime.tier import TierConfig, TierRegistry

_DUMMY_CFG = BackendConfig(provider="anthropic", model="m", api_key=None)  # type: ignore[arg-type]
_NONCE = "testnonce"
_HASH = "abc123hash"


class _RecordingConsent:
    """Consent stub that records its calls and returns a fixed verdict."""

    def __init__(self, *, allow: bool) -> None:
        self.allow = allow
        self.calls: list[tuple[str, str, str]] = []

    def is_enabled(self, persona_id: str, skill_name: str, content_hash: str) -> bool:
        self.calls.append((persona_id, skill_name, content_hash))
        return self.allow


def _persona() -> Persona:
    return Persona(
        persona_id="astrid",
        identity=PersonaIdentity(name="Astrid", role="assistant", background="bg"),
    )


def _skill(name: str, *, trust: SkillTrust) -> SkillSpec:
    return SkillSpec(
        name=name,
        description="A test skill.",
        path=Path(f"/tmp/{name}/SKILL.md"),
        content="Some genuine skill guidance to inject.",
        content_token_count=count_tokens("Some genuine skill guidance to inject."),
        trust=trust,
        provenance=SkillProvenance(
            source="github:acme/skills", source_ref="ref1", content_hash=_HASH
        ),
    )


def _registry(backend: ScriptedBackend) -> TierRegistry:
    reg = TierRegistry(
        {n: TierConfig(name=n, backend_config=_DUMMY_CFG) for n in ("frontier", "mid", "small")}
    )
    reg._cache = {"frontier": backend, "mid": backend, "small": backend}  # type: ignore[assignment]
    return reg


def _stores() -> dict[str, FakeStore]:
    return {k: FakeStore() for k in ("identity", "self_facts", "worldview", "episodic")}


def _chat_loop(
    skills: list[SkillSpec], *, consent: object | None = None, audit: object | None = None
) -> ConversationLoop:
    return ConversationLoop(
        persona=_persona(),
        stores=_stores(),  # type: ignore[arg-type]
        toolbox=Toolbox([], allow_list=None),
        skill_scanner=SkillScanner([]),
        skill_injector=SkillInjector(),
        scanned_skills=skills,
        history_manager=ConversationHistoryManager(compact_every=10, keep_recent=5),
        prompt_builder=PromptBuilder(),
        router=Router(),
        tier_registry=_registry(ScriptedBackend([], chat_script=[])),
        turn_log_writer=MemoryTurnLogWriter(),
        nonce_source=lambda: _NONCE,
        skill_consent=consent,  # type: ignore[arg-type]
        audit_logger=audit,  # type: ignore[arg-type]
    )


def _agentic_loop(
    skills: list[SkillSpec], *, consent: object | None = None, audit: object | None = None
) -> AgenticLoop:
    return AgenticLoop(
        persona=_persona(),
        stores=_stores(),  # type: ignore[arg-type]
        toolbox=Toolbox([], allow_list=None),
        skill_injector=SkillInjector(),
        scanned_skills=skills,
        prompt_builder=PromptBuilder(),
        router=Router(),
        tier_registry=_registry(ScriptedBackend([], chat_script=[])),
        nonce_source=lambda: _NONCE,
        skill_consent=consent,  # type: ignore[arg-type]
        audit_logger=audit,  # type: ignore[arg-type]
    )


async def _compose(loop: ConversationLoop, spec: SkillSpec) -> object:
    return await loop._compose_skill(
        spec, SkillCompositionState(budget=SkillInjector.TOKEN_BUDGET), None, None
    )


async def _activate_agentic(loop: AgenticLoop, spec: SkillSpec) -> list:
    context: list = []
    call = ToolCall(name="use_skill", args={"skill_name": spec.name}, call_id="c1")
    result = ToolResult(tool_name="use_skill", content="ok", data={"skill_name": spec.name})
    await loop._maybe_inject_skill(call, result, context)
    return context


class TestNewAuditVocabulary:
    def test_actions_and_store_sentinel_exist(self) -> None:
        assert AuditAction.SKILL_INJECTED.value == "skill_injected"
        assert AuditAction.SKILL_REFUSED.value == "skill_refused"


class TestConsentGateChat:
    @pytest.mark.asyncio
    async def test_default_deny_refuses_third_party(self) -> None:
        # No consent provider passed → loop defaults to DenyUnvettedConsent.
        audit = MemoryAuditLogger()
        loop = _chat_loop([_skill("evil", trust=SkillTrust.THIRD_PARTY)], audit=audit)
        composed = await _compose(loop, _skill("evil", trust=SkillTrust.THIRD_PARTY))

        # Not injected — content is None; persona gets an informative message.
        assert composed.content is None  # type: ignore[attr-defined]
        assert "not been approved" in composed.message  # type: ignore[attr-defined]
        # Exactly one SKILL_REFUSED event.
        events = audit.events
        assert len(events) == 1
        assert events[0].action is AuditAction.SKILL_REFUSED
        assert events[0].metadata["consent_state"] == "refused_no_consent"

    @pytest.mark.asyncio
    async def test_granted_consent_injects(self) -> None:
        audit = MemoryAuditLogger()
        consent = _RecordingConsent(allow=True)
        loop = _chat_loop(
            [_skill("ext", trust=SkillTrust.THIRD_PARTY)], consent=consent, audit=audit
        )
        composed = await _compose(loop, _skill("ext", trust=SkillTrust.THIRD_PARTY))

        assert composed.content is not None  # type: ignore[attr-defined]
        assert f"{_NONCE} tier=third_party" in composed.content  # type: ignore[attr-defined]
        # consent consulted with the spec's content_hash (the re-consent binding).
        assert consent.calls == [("astrid", "ext", _HASH)]
        events = audit.events
        assert len(events) == 1
        assert events[0].action is AuditAction.SKILL_INJECTED
        assert events[0].metadata["consent_state"] == "consented"

    @pytest.mark.asyncio
    async def test_builtin_skips_the_gate(self) -> None:
        consent = _RecordingConsent(allow=False)  # would refuse IF consulted
        audit = MemoryAuditLogger()
        loop = _chat_loop([_skill("b", trust=SkillTrust.BUILTIN)], consent=consent, audit=audit)
        composed = await _compose(loop, _skill("b", trust=SkillTrust.BUILTIN))

        assert composed.content is not None  # type: ignore[attr-defined]
        assert consent.calls == []  # builtin never consults consent
        assert audit.events[0].action is AuditAction.SKILL_INJECTED
        assert audit.events[0].metadata["consent_state"] == "builtin_implicit"

    @pytest.mark.asyncio
    async def test_vetted_skips_the_gate(self) -> None:
        consent = _RecordingConsent(allow=False)
        audit = MemoryAuditLogger()
        loop = _chat_loop([_skill("v", trust=SkillTrust.VETTED)], consent=consent, audit=audit)
        composed = await _compose(loop, _skill("v", trust=SkillTrust.VETTED))

        assert composed.content is not None  # type: ignore[attr-defined]
        assert consent.calls == []
        assert audit.events[0].metadata["consent_state"] == "vetted_implicit"

    @pytest.mark.asyncio
    async def test_community_is_gated(self) -> None:
        consent = _RecordingConsent(allow=False)
        loop = _chat_loop([_skill("c", trust=SkillTrust.COMMUNITY)], consent=consent)
        composed = await _compose(loop, _skill("c", trust=SkillTrust.COMMUNITY))
        assert composed.content is None  # type: ignore[attr-defined]
        assert consent.calls == [("astrid", "c", _HASH)]


class TestAuditMetadataAndCounts:
    @pytest.mark.asyncio
    async def test_injection_metadata_is_complete(self) -> None:
        audit = MemoryAuditLogger()
        consent = _RecordingConsent(allow=True)
        loop = _chat_loop(
            [_skill("ext", trust=SkillTrust.THIRD_PARTY)], consent=consent, audit=audit
        )
        await _compose(loop, _skill("ext", trust=SkillTrust.THIRD_PARTY))
        ev = audit.events[0]
        assert ev.store == "skill"
        assert ev.source.value == "system"
        assert ev.written_by == "github:acme/skills"
        assert ev.persona_id == "astrid"
        assert ev.metadata["trust"] == "third_party"
        assert ev.metadata["source"] == "github:acme/skills"
        assert ev.metadata["source_ref"] == "ref1"
        assert ev.metadata["content_hash"] == _HASH

    @pytest.mark.asyncio
    async def test_no_sink_is_inert_and_output_identical(self) -> None:
        # Audit None vs audit present → identical guarded output, no crash.
        consent_a = _RecordingConsent(allow=True)
        consent_b = _RecordingConsent(allow=True)
        no_audit = _chat_loop(
            [_skill("ext", trust=SkillTrust.THIRD_PARTY)], consent=consent_a, audit=None
        )
        with_audit = _chat_loop(
            [_skill("ext", trust=SkillTrust.THIRD_PARTY)],
            consent=consent_b,
            audit=MemoryAuditLogger(),
        )
        out_a = (await _compose(no_audit, _skill("ext", trust=SkillTrust.THIRD_PARTY))).content  # type: ignore[attr-defined]
        out_b = (await _compose(with_audit, _skill("ext", trust=SkillTrust.THIRD_PARTY))).content  # type: ignore[attr-defined]
        assert out_a is not None
        assert out_a == out_b  # the audit does not perturb the guard output


class TestConsentGateAgentic:
    @pytest.mark.asyncio
    async def test_default_deny_refuses_and_audits(self) -> None:
        audit = MemoryAuditLogger()
        loop = _agentic_loop([_skill("evil", trust=SkillTrust.THIRD_PARTY)], audit=audit)
        context = await _activate_agentic(loop, _skill("evil", trust=SkillTrust.THIRD_PARTY))

        # An informative system message, but NO enveloped skill content injected.
        assert len(context) == 1
        assert "not been approved" in context[0].content
        assert "<<<skill-guidance" not in context[0].content
        assert len(audit.events) == 1
        assert audit.events[0].action is AuditAction.SKILL_REFUSED

    @pytest.mark.asyncio
    async def test_granted_consent_injects_and_audits(self) -> None:
        audit = MemoryAuditLogger()
        loop = _agentic_loop(
            [_skill("ext", trust=SkillTrust.THIRD_PARTY)],
            consent=_RecordingConsent(allow=True),
            audit=audit,
        )
        context = await _activate_agentic(loop, _skill("ext", trust=SkillTrust.THIRD_PARTY))
        assert "<<<skill-guidance" in context[0].content
        assert len(audit.events) == 1
        assert audit.events[0].action is AuditAction.SKILL_INJECTED

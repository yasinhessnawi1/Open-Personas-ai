"""Skill consent enforcement + the skill-injection audit event (Spec S1, S1-D-6/D-7).

**Consent (S1-D-6).** Activating a skill above the trust threshold
(``trust.requires_consent`` — ``community`` / ``third_party``) requires explicit
owner consent *before* its content is injected. Consent is collected **once at
enable/install time** (Spec S3's frontend), bound to the skill's
``content_hash`` so an S2 content sync that changes the body invalidates stale
consent. S1 only **enforces** the consent state at activation; it does not run a
live consent prompt (the A3 async-approval surface is the wrong shape for a
synchronous mid-turn ``use_skill`` — S1-D-6).

The enforcement seam is :class:`SkillConsentPort`. S1 ships the port + a
**default-deny** stub (:class:`DenyUnvettedConsent`): an above-threshold skill is
**not injectable** until an explicit consent provider says yes. Spec S3
implements the real store against ``content_hash``; ``builtin`` / ``vetted``
skills never consult the port (they activate freely).

**Audit (S1-D-7).** :func:`skill_audit_event` builds the single
:class:`~persona.audit.AuditEvent` emitted per injection (``SKILL_INJECTED``) or
per consent refusal (``SKILL_REFUSED``), reusing the platform's existing
``AuditLogger`` posture — no new audit mechanism. Provenance + the consent state
ride in ``metadata``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from persona.audit import AuditAction, AuditEvent
from persona.schema.chunks import WriteSource
from persona.schema.skills import SkillTrust

if TYPE_CHECKING:
    from datetime import datetime

    from persona.schema.skills import SkillSpec

__all__ = [
    "DenyUnvettedConsent",
    "SkillConsentPort",
    "injection_consent_state",
    "skill_audit_event",
]


@runtime_checkable
class SkillConsentPort(Protocol):
    """The enable-time consent lookup the activation gate consults (S1-D-6).

    Implemented by Spec S3's consent store. S1 enforces against it; the persona
    must have consented to *this skill at this content hash* for an
    above-threshold skill to be injected.
    """

    def is_enabled(self, persona_id: str, skill_name: str, content_hash: str) -> bool:
        """Whether ``persona_id`` has consented to ``skill_name`` at ``content_hash``.

        Returns ``False`` for absent/denied/stale consent → the skill is not
        injected, the persona is unaffected (criterion 3).
        """
        ...


class DenyUnvettedConsent:
    """The default-deny consent stub (S1-D-6).

    Until Spec S3 wires a real consent store, every above-threshold skill is
    refused — the safe default: untrusted external content is **not** injected
    on the strength of an absent consent system. ``builtin`` / ``vetted`` skills
    never reach this (``trust.requires_consent`` is ``False`` for them).
    """

    def is_enabled(self, persona_id: str, skill_name: str, content_hash: str) -> bool:  # noqa: ARG002
        return False


def injection_consent_state(trust: SkillTrust) -> str:
    """The ``consent_state`` recorded for a successful injection at ``trust``.

    ``builtin`` / ``vetted`` inject without a consent gate (recorded as
    ``*_implicit``); ``community`` / ``third_party`` only reach injection when the
    consent gate passed (recorded as ``consented``).
    """
    if trust is SkillTrust.BUILTIN:
        return "builtin_implicit"
    if trust is SkillTrust.VETTED:
        return "vetted_implicit"
    return "consented"


def skill_audit_event(
    *,
    persona_id: str,
    spec: SkillSpec,
    action: AuditAction,
    consent_state: str,
    timestamp: datetime,
) -> AuditEvent:
    """Build the one :class:`AuditEvent` for a skill injection or refusal (S1-D-7).

    ``store="skill"`` (the non-store sentinel), ``source=system`` (skill
    activation is a platform action), ``written_by`` = the provenance source.
    Provenance (tier / source / source_ref / content_hash) + the consent state
    ride in ``metadata`` so the security trail is queryable. The caller supplies
    ``timestamp`` (core stays clock-free).
    """
    prov = spec.provenance
    metadata: dict[str, str] = {
        "skill_name": spec.name,
        "trust": spec.trust.value,
        "consent_state": consent_state,
    }
    if prov is not None:
        metadata["source"] = prov.source
        if prov.source_ref is not None:
            metadata["source_ref"] = prov.source_ref
        if prov.content_hash is not None:
            metadata["content_hash"] = prov.content_hash
    return AuditEvent(
        timestamp=timestamp,
        persona_id=persona_id,
        action=action,
        store="skill",
        source=WriteSource.SYSTEM,
        written_by=prov.source if prov is not None else None,
        metadata=metadata,
    )

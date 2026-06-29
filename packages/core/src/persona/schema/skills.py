"""Skill specification — definitions only.

Spec 04 ships the skill scanner, injector, and built-in skill packs. Spec 01
shipped ``SkillSpec`` with four fields (``name``, ``description``, ``path``,
``when_to_use``); spec 04 extends it additively per D-04-1 with three new
optional fields populated by the scanner at scan time.

A skill is a directory containing a ``SKILL.md`` (YAML front matter + Markdown
body) plus optional supporting code/prompts/assets. The path is recorded so
spec 04 can scan it.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path  # noqa: TC003 — Pydantic needs runtime access
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

__all__ = ["SkillProvenance", "SkillSpec", "SkillTrust"]


class SkillTrust(StrEnum):
    """How much a skill's injected content is trusted (Spec S1, S1-D-3).

    An ordered trust scale — ``builtin`` is fully trusted (repo-shipped),
    ``third_party`` is arbitrary external content. **The tier is assigned by
    the loader/source that produced the skill, NEVER read from the skill's own
    ``SKILL.md`` front matter** — a self-declared tier would let a malicious
    skill claim ``builtin`` and bypass the entire trust model. The local
    filesystem scanner assigns ``builtin``; Spec S2's external ingest assigns
    the lower tiers per-source.
    """

    BUILTIN = "builtin"
    VETTED = "vetted"
    COMMUNITY = "community"
    THIRD_PARTY = "third_party"

    @property
    def requires_consent(self) -> bool:
        """Whether activating a skill at this tier needs owner consent first.

        Per S1-D-4 the consent threshold sits above ``vetted``: ``community``
        and ``third_party`` are external-authored instructions the persona will
        follow, so they are consent-gated before injection; ``builtin`` and
        ``vetted`` (content we vetted) activate freely.
        """
        return self in (SkillTrust.COMMUNITY, SkillTrust.THIRD_PARTY)


class SkillProvenance(BaseModel):
    """Where a skill came from — carried through injection + audit (S1-D-5).

    Loader-assigned (never read from front matter, S1-D-3). ``content_hash`` is
    the re-consent trigger (S1-D-6): consent is granted for a specific body
    hash, so an S2 content sync that changes the body invalidates stale consent.

    Attributes:
        source: Origin label — ``"builtin"`` for repo skills; an S2 source id
            for external skills.
        source_uri: Repo/catalog URL where applicable; ``None`` for built-ins.
        source_ref: Repo commit / catalog version where available.
        content_hash: SHA-256 of the ``SKILL.md`` body. The version handle
            consent binds to.
        signature: Reserved for a future signed-skill story; carried but not
            verified in S1.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: str = Field(min_length=1)
    source_uri: str | None = None
    source_ref: str | None = None
    content_hash: str | None = None
    signature: str | None = None


class SkillSpec(BaseModel):
    """Where to find a skill pack and how to describe it.

    Attributes:
        name: Stable identifier referenced from the persona YAML's
            ``skills`` list (e.g., ``"legal_research"``).
        description: One-line description; injected into the skill index in
            the system prompt (spec 05).
        path: Directory containing the skill pack, including ``SKILL.md``.
        when_to_use: Optional short hint about when this skill is relevant.
            Pulled from ``SKILL.md`` front-matter by spec 04's scanner.
        tools_required: Tools the skill needs. Validated by the scanner
            against the persona's tool allow-list; missing tools log a
            WARNING but do not fail the skill. Added in spec 04 (D-04-1).
        content: Full ``SKILL.md`` body (after front matter). Populated by
            the scanner. Empty string when constructed outside a scan (e.g.,
            spec-01 tests). Added in spec 04 (D-04-1).
        content_token_count: Pre-computed ``cl100k_base`` token count of
            ``content``. Read by the injector without re-tokenising. Added
            in spec 04 (D-04-1, D-04-2).
        parameters: Optional JSON Schema (2020-12) describing the skill's
            call signature. Parsed from the SKILL.md front-matter ``metadata``
            block (D-24-X-skill-md-spec-compliance) and validated strictly at
            ``use_skill`` call time (D-24-8). Added in spec 24.
        not_for: Anti-examples — when explicitly NOT to use the skill. Added
            in spec 24.
        composes_with: Names of skills this one commonly chains with (D-24-4
            composition hints). Added in spec 24.
        output_format: Free-text description of the skill's output shape.
            Added in spec 24.
        token_budget: Optional per-skill override of the 2000-token skill
            content budget; ``None`` keeps the injector default. Added in
            spec 24 (D-24-5 hard-cap default retained).
        trust: The trust tier of this skill's content (Spec S1, S1-D-3/D-5).
            Assigned by the loader/source, never read from front matter.
            Defaults to ``builtin`` so spec-01/04/24 callers stay valid; the
            scanner sets it explicitly. Drives the consent gate
            (``trust.requires_consent``) and the subordination guard's tier
            label.
        provenance: Where this skill came from — source + (where available)
            repo/commit/content-hash/signature. ``None`` when constructed
            outside a scan. The ``content_hash`` is the re-consent trigger
            (S1-D-6). Added in spec S1.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    path: Path
    when_to_use: str | None = None
    # Spec 04 additive fields (D-04-1). All optional; defaults keep spec-01
    # callers working without modification.
    tools_required: list[str] = Field(default_factory=list)
    content: str = ""
    content_token_count: int = Field(default=0, ge=0)
    # Spec 24 additive v2-schema fields (D-24-X-skill-md-spec-compliance).
    # Populated by the scanner from the SKILL.md ``metadata`` block; all
    # optional so spec-01/spec-04 callers stay valid without modification.
    # ``parameters`` holds a raw JSON Schema dict (heterogeneous by nature —
    # ``Any`` is unavoidable here; it is validated at call time, not at scan).
    parameters: dict[str, Any] | None = None
    not_for: list[str] = Field(default_factory=list)
    composes_with: list[str] = Field(default_factory=list)
    output_format: str | None = None
    token_budget: int | None = Field(default=None, ge=1)
    # Spec S1 additive trust fields. Loader-assigned (never from front matter,
    # S1-D-3); defaults keep every prior caller valid (no-regression).
    trust: SkillTrust = SkillTrust.BUILTIN
    provenance: SkillProvenance | None = None

"""Tests for the S1 trust + provenance additions to ``SkillSpec`` (S1 T1).

Covers S1-D-3 (the ``SkillTrust`` taxonomy + the ``requires_consent``
threshold of S1-D-4) and S1-D-5 (the nested ``SkillProvenance`` + the
top-level ``trust`` field, both optional with no-regression defaults).
"""

from __future__ import annotations

from pathlib import Path

import pytest
from persona.schema.skills import SkillProvenance, SkillSpec, SkillTrust


class TestSkillTrust:
    def test_four_tiers_exist(self) -> None:
        assert {t.value for t in SkillTrust} == {
            "builtin",
            "vetted",
            "community",
            "third_party",
        }

    @pytest.mark.parametrize(
        ("tier", "expected"),
        [
            (SkillTrust.BUILTIN, False),
            (SkillTrust.VETTED, False),
            (SkillTrust.COMMUNITY, True),
            (SkillTrust.THIRD_PARTY, True),
        ],
    )
    def test_requires_consent_gates_above_vetted(self, tier: SkillTrust, expected: bool) -> None:
        # S1-D-4: consent is required for everything strictly above ``vetted``
        # (community + third_party are external-authored instructions the
        # persona will follow); builtin + vetted activate freely.
        assert tier.requires_consent is expected


class TestSkillProvenance:
    def test_frozen_and_forbids_extra(self) -> None:
        prov = SkillProvenance(source="builtin")
        with pytest.raises(Exception):  # noqa: B017,PT011 — frozen → mutation raises
            prov.source = "evil"  # type: ignore[misc]
        with pytest.raises(Exception):  # noqa: B017,PT011 — extra=forbid
            SkillProvenance(source="x", bogus="y")  # type: ignore[call-arg]

    def test_source_required_optionals_default_none(self) -> None:
        prov = SkillProvenance(source="builtin")
        assert prov.source == "builtin"
        assert prov.source_uri is None
        assert prov.source_ref is None
        assert prov.content_hash is None
        assert prov.signature is None

    def test_carries_full_provenance(self) -> None:
        prov = SkillProvenance(
            source="github:acme/skills",
            source_uri="https://github.com/acme/skills",
            source_ref="abc1234",
            content_hash="deadbeef",
            signature="sig",
        )
        assert prov.source_ref == "abc1234"
        assert prov.content_hash == "deadbeef"


class TestSkillSpecDefaults:
    def test_trust_defaults_to_builtin_provenance_none(self) -> None:
        # No-regression by construction: every spec-01/04/24 caller that omits
        # the new fields still validates, defaulting to the trusted tier.
        spec = SkillSpec(name="s", description="d", path=Path("/tmp/s"))
        assert spec.trust is SkillTrust.BUILTIN
        assert spec.provenance is None

    def test_accepts_explicit_trust_and_provenance(self) -> None:
        spec = SkillSpec(
            name="s",
            description="d",
            path=Path("/tmp/s"),
            trust=SkillTrust.THIRD_PARTY,
            provenance=SkillProvenance(source="github:acme/skills", content_hash="abc"),
        )
        assert spec.trust is SkillTrust.THIRD_PARTY
        assert spec.provenance is not None
        assert spec.provenance.source == "github:acme/skills"

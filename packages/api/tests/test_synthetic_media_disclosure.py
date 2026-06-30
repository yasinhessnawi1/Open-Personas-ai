"""Synthetic-media disclosure — derivation + surfaces (Spec R3, Group C + D).

EU AI Act Art. 50: the recipient-facing "AI-generated" label is *derived* from
the stored structural signal, never guessed. These unit tests pin:

- **Group C (verify)** — the chat-image surface stamps ``PersistedArtifact``'s new
  provenance default + the structural ``source="generated"`` sidecar (the latter is
  already covered by ``test_f5_t05_imagegen_sidecar`` / ``test_api_workspace_persister``;
  here we pin the R3 disclosure default on the artifact the SSE render path carries).
- **Group D (disclose)** — the single derivation (``ai_generated_from_source``) +
  its presence on every disclosure surface (``ArtifactMetadataView``,
  ``PersonaDetail``-side derivation, ``PersistedArtifact``). Riding the existing
  structural signal, not duplicating it (R3-D-4).
"""

from __future__ import annotations

import pytest
from persona.schema.tools import PersistedArtifact
from persona_api.schemas import ArtifactMetadataView, PersonaDetail
from persona_api.services.provenance import (
    ai_generated_from_source,
    avatar_ai_generated_from_source,
)

# ---------------------------------------------------------------------------
# Group D — the single derivation (the Art. 50 invariant: derive, never guess).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("generated", True),
        ("uploaded", False),
        (None, None),  # legacy / unknown — no claim (R3-D-5)
        ("nonsense", None),  # out-of-vocab → conservative unknown (R3-R-1)
    ],
)
def test_ai_generated_derivation(source: str | None, expected: bool | None) -> None:
    assert ai_generated_from_source(source) is expected
    # The avatar alias is the SAME derivation (one source of truth).
    assert avatar_ai_generated_from_source(source) is expected


# ---------------------------------------------------------------------------
# Group D — PersistedArtifact carries provenance for the SSE inline render.
# ---------------------------------------------------------------------------


def test_persisted_artifact_defaults_ai_generated_true() -> None:
    """Every artifact on ``ToolResult.artifacts`` is a system-produced output, so
    the provenance defaults True — the SSE inline-render path now discloses (it
    previously carried none)."""
    art = PersistedArtifact(workspace_path="uploads/x.png", mime_type="image/png", size_bytes=10)
    assert art.ai_generated is True
    # It serialises onto the payload (the events.py forward path is a.model_dump()).
    assert art.model_dump()["ai_generated"] is True


def test_persisted_artifact_extra_forbidden_and_frozen() -> None:
    """The frozen + extra='forbid' contract still holds (no silent drift)."""
    art = PersistedArtifact(workspace_path="uploads/x.png", mime_type="image/png", size_bytes=10)
    with pytest.raises(Exception):  # noqa: B017, PT011 — frozen model rejects mutation
        art.ai_generated = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Group D — the disclosure rides the existing structural signal on each surface.
# ---------------------------------------------------------------------------


def test_artifact_metadata_view_carries_derived_disclosure() -> None:
    from datetime import UTC, datetime

    view = ArtifactMetadataView(
        source="generated",
        ai_generated=ai_generated_from_source("generated"),
        type="image",
        producing_spec="15",
        conversation_id=None,
        created_at=datetime.now(UTC),
        original_name=None,
    )
    # Raw structural signal preserved (no breaking change) AND the derived label.
    assert view.source == "generated"
    assert view.ai_generated is True


def test_persona_detail_carries_avatar_provenance_and_disclosure() -> None:
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    detail = PersonaDetail(
        id="p1",
        yaml="name: A",
        schema_version="1.0",
        avatar_url="uploads/a.png",
        avatar_source="generated",
        avatar_ai_generated=avatar_ai_generated_from_source("generated"),
        created_at=now,
        updated_at=now,
    )
    assert detail.avatar_source == "generated"
    assert detail.avatar_ai_generated is True


def test_persona_detail_legacy_avatar_source_is_unknown() -> None:
    """A legacy persona (no provenance) discloses None = unknown — never a guess."""
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    detail = PersonaDetail(
        id="p1",
        yaml="name: A",
        schema_version="1.0",
        avatar_url="uploads/legacy.png",
        avatar_source=None,
        avatar_ai_generated=avatar_ai_generated_from_source(None),
        created_at=now,
        updated_at=now,
    )
    assert detail.avatar_source is None
    assert detail.avatar_ai_generated is None

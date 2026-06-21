"""Unit tests for canonical entity resolution (Spec K0, T5 / D-K0-9).

Fakes the transport + embedder so the deterministic three-way verdict and the
lexical scoring are tested with no DB and no LLM. The fake ``find_entity_by_text``
mirrors the real exact-match SQL (canonical name + alias surfaces, normalized);
``entity_candidates`` returns crafted ``(entity, distance)`` so embedding
similarity is controlled per test.
"""

# ruff: noqa: ARG002 — fakes deliberately ignore some args
from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest
from persona.graph import entities as entities_module
from persona.graph.config import GraphSettings
from persona.graph.entities import (
    PostgresEntityRegistry,
    jaro_winkler,
    lexical_similarity,
    normalize_surface,
)
from persona.graph.errors import EntityResolutionError
from persona.graph.models import CanonicalEntity, EntityAlias, NodeProvenance
from persona.graph.protocol import EntityRegistry, ResolutionDecision
from persona.schema.chunks import WriteSource

NOW = datetime(2026, 6, 21, 12, 0, tzinfo=UTC)


def _entity(eid: str, name: str, *aliases: str) -> CanonicalEntity:
    return CanonicalEntity(
        id=eid,
        canonical_name=name,
        aliases=tuple(EntityAlias(surface=a) for a in aliases),
        created_at=NOW,
    )


class _FakeBackend:
    """In-memory transport: real exact-match logic, crafted embedding candidates."""

    def __init__(self) -> None:
        self.entities: dict[str, CanonicalEntity] = {}
        self.candidates: list[tuple[CanonicalEntity, float]] = []
        self.added_aliases: list[tuple[str, EntityAlias]] = []
        self.inserted: list[CanonicalEntity] = []

    def register(self, entity: CanonicalEntity) -> None:
        self.entities[entity.id] = entity

    def find_entity_by_text(self, owner_id: str, normalized_name: str) -> CanonicalEntity | None:
        for e in self.entities.values():
            surfaces = [e.canonical_name, *(a.surface for a in e.aliases)]
            if any(normalize_surface(s) == normalized_name for s in surfaces):
                return e
        return None

    def entity_candidates(
        self, owner_id: str, name_vector: object, top_k: int
    ) -> list[tuple[CanonicalEntity, float]]:
        return self.candidates[:top_k]

    def count_entities(self, owner_id: str) -> int:
        return len(self.inserted)

    def insert_entity(self, owner_id: str, entity: CanonicalEntity, name_embedding: object) -> None:
        self.inserted.append(entity)
        self.entities[entity.id] = entity

    def get_entity(self, owner_id: str, entity_id: str) -> CanonicalEntity | None:
        return self.entities.get(entity_id)

    def add_alias(self, owner_id: str, entity_id: str, alias: EntityAlias) -> None:
        self.added_aliases.append((entity_id, alias))


class _FakeEmbedder:
    model_name = "fake"

    @property
    def dimension(self) -> int:
        return 384

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 384 for _ in texts]


def _registry(backend: _FakeBackend, **settings: float) -> PostgresEntityRegistry:
    cfg = GraphSettings(**settings) if settings else GraphSettings()  # type: ignore[arg-type]
    return PostgresEntityRegistry(backend=backend, embedder=_FakeEmbedder(), settings=cfg)


def _dist(sim: float) -> float:
    """Cosine distance for a target embedding similarity."""
    return 1.0 - sim


# ----- lexical primitives --------------------------------------------------


def test_normalize_surface_lowers_and_collapses() -> None:
    assert normalize_surface("  Dr.   Hansen ") == "dr. hansen"


def test_jaro_winkler_identical_and_disjoint() -> None:
    assert jaro_winkler("dr hansen", "dr hansen") == 1.0
    assert jaro_winkler("abc", "xyz") == 0.0
    # near-spelling of a name scores high (the over-eager danger lexical alone poses)
    assert jaro_winkler("dr hanson", "dr hansen") > 0.9


def test_lexical_similarity_picks_best_of_name_and_aliases() -> None:
    ent = _entity("e1", "Dr. Hansen", "my doctor", "the GP")
    assert lexical_similarity("my doctor", ent) == 1.0  # exact alias
    assert lexical_similarity("dr. hansen", ent) == 1.0  # exact canonical


# ----- the three-way verdict ----------------------------------------------


def test_empty_registry_returns_separate() -> None:
    verdict = _registry(_FakeBackend()).resolve("u1", "Dr. Hansen")
    assert verdict.decision is ResolutionDecision.SEPARATE


def test_exact_canonical_match_merges() -> None:
    b = _FakeBackend()
    b.register(_entity("u1::entity::00000001", "Dr. Hansen"))
    verdict = _registry(b).resolve("u1", "  dr. HANSEN ")
    assert verdict.decision is ResolutionDecision.MERGE
    assert verdict.canonical_id == "u1::entity::00000001"


def test_exact_alias_match_merges() -> None:
    b = _FakeBackend()
    b.register(_entity("u1::entity::00000001", "Dr. Hansen", "my doctor"))
    verdict = _registry(b).resolve("u1", "My Doctor")
    assert verdict.decision is ResolutionDecision.MERGE
    assert verdict.canonical_id == "u1::entity::00000001"


def test_strong_embedding_agreement_merges_even_if_lexically_distinct() -> None:
    b = _FakeBackend()
    ent = _entity("u1::entity::00000001", "Dr. Hansen")
    b.candidates = [(ent, _dist(0.97))]  # 0.97 >= 0.92 merge bar
    verdict = _registry(b).resolve("u1", "the physician")  # lexically unrelated
    assert verdict.decision is ResolutionDecision.MERGE
    assert verdict.canonical_id == ent.id


def test_low_signals_separate() -> None:
    b = _FakeBackend()
    ent = _entity("u1::entity::00000001", "Dr. Hansen")
    b.candidates = [(ent, _dist(0.40))]  # weak embedding, lexically unrelated mention
    verdict = _registry(b).resolve("u1", "weekend hiking plans")
    assert verdict.decision is ResolutionDecision.SEPARATE


def test_over_eager_guard_lexical_alone_never_auto_merges() -> None:
    # "Dr. Hanson" (a DIFFERENT person) vs registered "Dr. Hansen": high lexical
    # (~0.95) but only MODERATE embedding (0.85 < 0.92). Must NOT merge — it goes
    # to the LLM review band, not a silent wrong merge.
    b = _FakeBackend()
    ent = _entity("u1::entity::00000001", "Dr. Hansen")
    b.candidates = [(ent, _dist(0.85))]
    verdict = _registry(b).resolve("u1", "Dr. Hanson")
    assert verdict.decision is ResolutionDecision.AMBIGUOUS
    assert verdict.canonical_id is None
    assert verdict.candidates[0].entity_id == ent.id  # handed to K2's judge


def test_over_shy_guard_registered_alias_merges_not_separate() -> None:
    # A known alias must resolve to its entity (no fragmentation), even though the
    # alias's embedding is nowhere near the canonical name's.
    b = _FakeBackend()
    b.register(_entity("u1::entity::00000001", "Dr. Hansen", "the GP"))
    b.candidates = []  # embedding leg finds nothing for "the GP"
    verdict = _registry(b).resolve("u1", "the GP")
    assert verdict.decision is ResolutionDecision.MERGE
    assert verdict.canonical_id == "u1::entity::00000001"


def test_ambiguous_band_defers_to_k2_with_candidates() -> None:
    b = _FakeBackend()
    e1 = _entity("u1::entity::00000001", "Dr. Hansen")
    e2 = _entity("u1::entity::00000002", "Doctor Hanssen")
    b.candidates = [(e1, _dist(0.86)), (e2, _dist(0.84))]
    verdict = _registry(b).resolve("u1", "Dr Hansenn")
    assert verdict.decision is ResolutionDecision.AMBIGUOUS
    assert verdict.canonical_id is None
    assert {c.entity_id for c in verdict.candidates} <= {e1.id, e2.id}
    # candidates are score-ordered for the judge
    scores = [c.score for c in verdict.candidates]
    assert scores == sorted(scores, reverse=True)


def test_alias_heavy_fixture_resolves_to_one_canonical_entity() -> None:
    # criterion 3: my doctor / Dr. Hansen / the GP → ONE entity, not three families.
    b = _FakeBackend()
    one = _entity("u1::entity::00000001", "Dr. Hansen", "my doctor", "the GP")
    b.register(one)
    reg = _registry(b)
    ids = {reg.resolve("u1", m).canonical_id for m in ("Dr. Hansen", "my doctor", "the GP")}
    assert ids == {"u1::entity::00000001"}


def test_empty_mention_raises() -> None:
    with pytest.raises(EntityResolutionError, match="empty mention"):
        _registry(_FakeBackend()).resolve("u1", "   ")


# ----- LLM-free guarantee --------------------------------------------------


def test_registry_constructor_has_no_llm_dependency() -> None:
    params = set(inspect.signature(PostgresEntityRegistry.__init__).parameters) - {"self"}
    assert params == {"backend", "embedder", "settings"}


def test_entities_module_imports_no_chat_backend() -> None:
    src = inspect.getsource(entities_module)
    assert "ChatBackend" not in src
    assert ".chat(" not in src


def test_registry_satisfies_protocol() -> None:
    assert isinstance(_registry(_FakeBackend()), EntityRegistry)


# ----- create / alias write paths -----------------------------------------


def test_create_entity_generates_id_and_embeds_name() -> None:
    b = _FakeBackend()
    ent = _registry(b).create_entity("u1", canonical_name="Dr. Hansen")
    assert ent.id == "u1::entity::00000000"
    assert b.inserted[0].canonical_name == "Dr. Hansen"


def test_create_entity_carries_provenance_and_aliases() -> None:
    b = _FakeBackend()
    prov = NodeProvenance(source=WriteSource.PERSONA_SELF, written_at=NOW)
    ent = _registry(b).create_entity(
        "u1", canonical_name="X", aliases=(EntityAlias(surface="x"),), provenance=prov
    )
    assert ent.provenance is prov
    assert ent.aliases[0].surface == "x"


def test_add_alias_delegates_to_backend() -> None:
    b = _FakeBackend()
    _registry(b).add_alias("u1", "u1::entity::00000001", EntityAlias(surface="the GP"))
    assert b.added_aliases == [("u1::entity::00000001", EntityAlias(surface="the GP"))]


# ----- config bands --------------------------------------------------------


def test_settings_reject_separate_above_merge() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="alias_separate_threshold must be <="):
        GraphSettings(alias_merge_threshold=0.8, alias_separate_threshold=0.9)


def test_settings_defaults_are_the_research_priors() -> None:
    s = GraphSettings()
    assert s.alias_merge_threshold == 0.92
    assert s.alias_separate_threshold == 0.80
    assert s.alias_candidate_limit == 15

"""Canonical entity resolution — deterministic, LLM-free (Spec K0, T5 / D-K0-9).

K0 owns the canonical-entity registry and a **deterministic three-way verdict**
(``MERGE`` / ``SEPARATE`` / ``AMBIGUOUS`` + candidates). It NEVER calls an LLM:
the AMBIGUOUS review band is handed to **K2's** binary LLM judge, which then calls
back via :meth:`create_entity` / :meth:`add_alias`. This keeps persona-core's
store layer LLM-free and unit-testable without any model.

The resolver is the Fellegi-Sunter three-zone rule (research §2.2):

1. **Exact lookup** (canonical name or a registered alias, case/whitespace-
   insensitive) → ``MERGE`` at confidence 1.0. Safe: identical surface forms.
   This is how a registered alias ("my doctor") resolves to its entity even
   though its embedding is nowhere near the canonical name's.
2. **Embedding candidate-gen → score.** Cosine-nearest registry entities are
   scored by embedding similarity AND lexical (Jaro-Winkler over the canonical
   name + every alias). Strong *embedding* agreement (``>= alias_merge_threshold``)
   → ``MERGE`` (catches spelling/punctuation variants of the same name).
3. **Zones.** Otherwise, if the best combined score clears ``alias_separate_threshold``
   → ``AMBIGUOUS`` (the review band, for K2). Below it → ``SEPARATE``.

**Precision bias (F0.5, D-K0-9):** lexical similarity ALONE never auto-merges —
it only promotes a candidate into the AMBIGUOUS band. A near-spelling of a
*different* person ("Dr. Hanson" vs "Dr. Hansen") therefore goes to the LLM judge,
never to a silent wrong merge (which is catastrophic and transitive). Only an
exact surface match or strong embedding agreement merges automatically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from persona.graph.errors import EntityResolutionError
from persona.graph.models import CanonicalEntity, EntityAlias, make_entity_id
from persona.graph.protocol import EntityCandidate, ResolutionDecision, ResolutionVerdict

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persona.graph.config import GraphSettings
    from persona.graph.models import NodeProvenance
    from persona.stores.embedder import Embedder

__all__ = ["PostgresEntityRegistry", "jaro_winkler", "lexical_similarity", "normalize_surface"]


# ----- lexical similarity (hand-rolled; no new dependency) ------------------


def normalize_surface(surface: str) -> str:
    """Lower-case + whitespace-collapse a surface form (the exact-match key)."""
    return " ".join(surface.lower().split())


def _jaro(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    match_dist = max(max(len1, len2) // 2 - 1, 0)
    s1_matched = [False] * len1
    s2_matched = [False] * len2
    matches = 0
    for i in range(len1):
        start, end = max(0, i - match_dist), min(i + match_dist + 1, len2)
        for j in range(start, end):
            if s2_matched[j] or s1[i] != s2[j]:
                continue
            s1_matched[i] = s2_matched[j] = True
            matches += 1
            break
    if matches == 0:
        return 0.0
    transpositions = 0
    k = 0
    for i in range(len1):
        if not s1_matched[i]:
            continue
        while not s2_matched[k]:
            k += 1
        if s1[i] != s2[k]:
            transpositions += 1
        k += 1
    half_t = transpositions // 2
    return (matches / len1 + matches / len2 + (matches - half_t) / matches) / 3.0


def jaro_winkler(s1: str, s2: str, *, prefix_weight: float = 0.1, max_prefix: int = 4) -> float:
    """Jaro-Winkler string similarity in [0, 1] (prefix-weighted; names regime)."""
    jaro = _jaro(s1, s2)
    prefix = 0
    for a, b in zip(s1, s2, strict=False):
        if a != b:
            break
        prefix += 1
        if prefix == max_prefix:
            break
    return jaro + prefix * prefix_weight * (1.0 - jaro)


def lexical_similarity(normalized_mention: str, entity: CanonicalEntity) -> float:
    """Best Jaro-Winkler of the mention vs the entity's canonical name + aliases."""
    surfaces = [entity.canonical_name, *(a.surface for a in entity.aliases)]
    return max(jaro_winkler(normalized_mention, normalize_surface(s)) for s in surfaces)


# ----- the registry's data-access seam (structural; PostgresGraphBackend fits) --


class _EntityBackend(Protocol):
    """The transport surface the registry composes (PostgresGraphBackend satisfies it)."""

    def find_entity_by_text(
        self, owner_id: str, normalized_name: str
    ) -> CanonicalEntity | None: ...
    def entity_candidates(
        self, owner_id: str, name_vector: Sequence[float], top_k: int
    ) -> list[tuple[CanonicalEntity, float]]: ...
    def count_entities(self, owner_id: str) -> int: ...
    def insert_entity(
        self, owner_id: str, entity: CanonicalEntity, name_embedding: Sequence[float]
    ) -> None: ...
    def get_entity(self, owner_id: str, entity_id: str) -> CanonicalEntity | None: ...
    def add_alias(self, owner_id: str, entity_id: str, alias: EntityAlias) -> None: ...


class PostgresEntityRegistry:
    """Deterministic, LLM-free canonical-entity registry (implements ``EntityRegistry``).

    Composes a transport (the Postgres graph backend) + an injected
    :class:`~persona.stores.embedder.Embedder`. No LLM client, no network — the
    constructor takes only ``backend`` / ``embedder`` / ``settings`` (asserted in
    tests). The AMBIGUOUS band is K2's to judge.
    """

    def __init__(
        self,
        *,
        backend: _EntityBackend,
        embedder: Embedder,
        settings: GraphSettings | None = None,
    ) -> None:
        from persona.graph.config import GraphSettings as _Settings

        self._backend = backend
        self._embedder = embedder
        self._settings = settings or _Settings()

    def resolve(self, owner_id: str, mention: str) -> ResolutionVerdict:
        norm = normalize_surface(mention)
        if not norm:
            raise EntityResolutionError("empty mention", context={"mention": mention})

        # 1. Exact surface match (canonical or a registered alias) → MERGE.
        exact = self._backend.find_entity_by_text(owner_id, norm)
        if exact is not None:
            return ResolutionVerdict(decision=ResolutionDecision.MERGE, canonical_id=exact.id)

        # 2. Embedding candidate-gen, then score (embedding + lexical).
        vec = self._embedder.encode([mention])[0]
        candidates = self._backend.entity_candidates(
            owner_id, vec, self._settings.alias_candidate_limit
        )
        if not candidates:
            return ResolutionVerdict(decision=ResolutionDecision.SEPARATE)

        scored = [
            (ent, 1.0 - distance, lexical_similarity(norm, ent)) for ent, distance in candidates
        ]

        # MERGE only on strong EMBEDDING agreement (exact handled above); lexical
        # alone never auto-merges — it promotes to the review band (precision bias).
        best_ent, best_emb, _ = max(scored, key=lambda t: t[1])
        if best_emb >= self._settings.alias_merge_threshold:
            return ResolutionVerdict(decision=ResolutionDecision.MERGE, canonical_id=best_ent.id)

        # 3. Zones: anything clearing the separate bar (by either signal) is the
        # AMBIGUOUS review band for K2; below it is SEPARATE.
        in_band = [
            (ent, max(emb, lex))
            for ent, emb, lex in scored
            if max(emb, lex) >= self._settings.alias_separate_threshold
        ]
        if not in_band:
            return ResolutionVerdict(decision=ResolutionDecision.SEPARATE)
        in_band.sort(key=lambda t: t[1], reverse=True)
        return ResolutionVerdict(
            decision=ResolutionDecision.AMBIGUOUS,
            candidates=tuple(
                EntityCandidate(
                    entity_id=ent.id, canonical_name=ent.canonical_name, score=round(s, 4)
                )
                for ent, s in in_band
            ),
        )

    def get_entity(self, owner_id: str, entity_id: str) -> CanonicalEntity | None:
        return self._backend.get_entity(owner_id, entity_id)

    def create_entity(
        self,
        owner_id: str,
        *,
        canonical_name: str,
        aliases: tuple[EntityAlias, ...] = (),
        provenance: NodeProvenance | None = None,
    ) -> CanonicalEntity:
        index = self._backend.count_entities(owner_id)
        entity = CanonicalEntity(
            id=make_entity_id(owner_id, index),
            canonical_name=canonical_name,
            aliases=aliases,
            provenance=provenance,
            created_at=datetime.now(UTC),
        )
        name_embedding = self._embedder.encode([canonical_name])[0]
        self._backend.insert_entity(owner_id, entity, name_embedding)
        return entity

    def add_alias(self, owner_id: str, entity_id: str, alias: EntityAlias) -> None:
        self._backend.add_alias(owner_id, entity_id, alias)

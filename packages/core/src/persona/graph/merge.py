"""The merge engine — the coherence heart (Spec K0, T6a / D-K0-1/2/4).

Turns a K2 :class:`~persona.graph.protocol.KnowledgeCandidate` into a graph
mutation that keeps an infinitely-growing graph an accumulating *understanding*
rather than a *log*:

- **Extend vs create** (D-K0-1): the candidate's content is embedded once; if its
  nearest existing node is within ``merge_extend_threshold`` it **extends** that
  node, else a new node is **created** and auto-linked. The threshold is the
  make-or-break coherence parameter — config-driven, F0.5 precision-biased, and
  flagged for a real-data re-tune (:class:`~persona.graph.config.GraphSettings`).
- **Accumulate in place + provenance, NO silent overwrite** (D-K0-4): extending
  appends the new content (de-duplicated) and appends a provenance entry — the
  node grows with a provenance trail; it does NOT spawn a ``superseded_by`` chain.
  An UPDATE/CONTRADICT intent replaces the content with the user's current account
  while the provenance entry records the change (the change is recorded, not
  silent).
- **Auto semantic links** (D-K0-2): on create/extend the node is wired to its
  nearest neighbours above ``semantic_link_threshold`` (looser than the merge
  bar — a navigable link, not a merge), capped at ``max_semantic_links`` and
  re-evaluated on extend.
- **Idempotent** (K2 crit 8): re-merging an identical candidate adds nothing — the
  extend finds the node and the content is already present → a no-op.

**Consumes pre-resolved ``entity_ids``** (T2 design-call #2): merge does NOT call
the entity registry's ``resolve()`` — K2 resolves entities first (and owns the LLM
judge on the AMBIGUOUS band) and hands the resolved ids in the candidate. Entity /
temporal / causal typed-link *attachment* is T6b. Index sync is T8 (this engine
mutates Postgres only; the store wraps it to sync the dense index + emit audit).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Protocol

from persona.graph.errors import NodeMergeError
from persona.graph.models import ConceptNode, LinkType, TypedLink, make_edge_id, make_node_id
from persona.graph.protocol import KnowledgeCandidate, MergeAction, MergeOutcome, UpdateIntent

if TYPE_CHECKING:
    from collections.abc import Sequence

    from persona.graph.config import GraphSettings
    from persona.stores.embedder import Embedder

__all__ = ["MergeEngine"]


def accumulate(existing: str, addition: str) -> str:
    """Append ``addition`` to ``existing`` unless it is empty or already present.

    The de-duplication (substring check) is what makes an identical re-merge a
    no-op (idempotency) and stops a node's content from accreting duplicates.
    """
    new = addition.strip()
    if not new or new in existing:
        return existing
    return f"{existing}\n{new}" if existing.strip() else new


class _MergeBackend(Protocol):
    """The transport surface the merge engine composes (PostgresGraphBackend fits)."""

    def dense_query(
        self,
        owner_id: str,
        query_vector: Sequence[float],
        top_k: int,
        *,
        allowed_surrogates: Sequence[int] | None = None,
    ) -> list[ConceptNode]: ...
    def count_nodes(self, owner_id: str) -> int: ...
    def get_node(self, owner_id: str, node_id: str) -> ConceptNode | None: ...
    def insert_node(self, owner_id: str, node: ConceptNode, embedding: Sequence[float]) -> int: ...
    def update_node(
        self, owner_id: str, node: ConceptNode, embedding: Sequence[float]
    ) -> int | None: ...
    def upsert_edge(self, owner_id: str, link: TypedLink) -> None: ...
    def delete_links_from(self, owner_id: str, node_id: str, link_type: LinkType) -> None: ...
    def associate_entities(
        self, owner_id: str, node_id: str, entity_ids: Sequence[str]
    ) -> None: ...


class MergeEngine:
    """Canonicalise→extend-vs-create→link path over the Postgres transport (T6a).

    Composes the transport + an injected embedder + settings. LLM-free and
    index-free (T8 wraps it for index sync + audit). The merge happens off the
    critical path (K2 §2), so matching uses exact pgvector cosine over the durable
    embeddings — exactness over speed.
    """

    def __init__(
        self,
        *,
        backend: _MergeBackend,
        embedder: Embedder,
        settings: GraphSettings | None = None,
    ) -> None:
        from persona.graph.config import GraphSettings as _Settings

        self._backend = backend
        self._embedder = embedder
        self._settings = settings or _Settings()

    def merge(self, owner_id: str, candidate: KnowledgeCandidate) -> MergeOutcome:
        vec = self._embedder.encode([candidate.content])[0]

        # Explicit update/contradiction → evolve a named node (D-K0-4).
        if candidate.update_intent in (UpdateIntent.UPDATE, UpdateIntent.CONTRADICT):
            return self._evolve(owner_id, candidate, vec)

        # Extend-vs-create on the merge threshold (D-K0-1).
        nearest = self._backend.dense_query(owner_id, vec, 1)
        if nearest and _similarity(nearest[0]) >= self._settings.merge_extend_threshold:
            return self._extend(owner_id, nearest[0], candidate, vec)
        return self._create(owner_id, candidate, vec)

    # -- create -------------------------------------------------------------

    def _create(
        self, owner_id: str, candidate: KnowledgeCandidate, vec: Sequence[float]
    ) -> MergeOutcome:
        node = ConceptNode(
            id=make_node_id(owner_id, self._backend.count_nodes(owner_id)),
            node_kind=candidate.node_kind,
            concept_name=candidate.concept_name,
            content=candidate.content,
            wellbeing_category=candidate.wellbeing_category,
            provenance=(candidate.provenance,),
            created_at=datetime.now(UTC),
        )
        self._backend.insert_node(owner_id, node, vec)
        link_ids = self._form_semantic_links(owner_id, node, vec, re_eval=False)
        link_ids += self._attach_typed(owner_id, node.id, candidate)
        return MergeOutcome(
            action=MergeAction.CREATED,
            node_id=node.id,
            created_link_ids=tuple(link_ids),
            entity_ids=candidate.entity_ids,
        )

    # -- extend (accumulate) ------------------------------------------------

    def _extend(
        self,
        owner_id: str,
        target: ConceptNode,
        candidate: KnowledgeCandidate,
        candidate_vec: Sequence[float],  # noqa: ARG002 — re-embedded from accumulated content
    ) -> MergeOutcome:
        new_content = accumulate(target.content, candidate.content)
        if new_content == target.content:
            # Idempotent / no-new-knowledge: the content is already present (K2 crit 8).
            # Entity associations / proposed links are still recorded — idempotently.
            link_ids = self._attach_typed(owner_id, target.id, candidate)
            return MergeOutcome(
                action=MergeAction.EXTENDED,
                node_id=target.id,
                created_link_ids=tuple(link_ids),
                entity_ids=candidate.entity_ids,
            )
        node = self._rebuilt(target, content=new_content, candidate=candidate)
        new_vec = self._embedder.encode([new_content])[0]
        self._backend.update_node(owner_id, node, new_vec)
        link_ids = self._form_semantic_links(owner_id, node, new_vec, re_eval=True)
        link_ids += self._attach_typed(owner_id, node.id, candidate)
        return MergeOutcome(
            action=MergeAction.EXTENDED,
            node_id=node.id,
            created_link_ids=tuple(link_ids),
            entity_ids=candidate.entity_ids,
        )

    # -- update / contradiction (D-K0-4) ------------------------------------

    def _evolve(
        self, owner_id: str, candidate: KnowledgeCandidate, vec: Sequence[float]
    ) -> MergeOutcome:
        if not candidate.target_node_id:
            raise NodeMergeError(
                "update/contradict requires target_node_id",
                context={"intent": str(candidate.update_intent), "concept": candidate.concept_name},
            )
        target = self._backend.get_node(owner_id, candidate.target_node_id)
        if target is None:
            raise NodeMergeError(
                "update/contradict target not found",
                context={"target_node_id": candidate.target_node_id, "owner_id": owner_id},
            )
        # Current account wins for retrieval; the appended provenance entry records
        # the change (NOT a silent overwrite — D-K0-4). The prior content is retained
        # in the provenance trail's reason for audit/K5.
        node = self._rebuilt(
            target,
            content=candidate.content,
            candidate=candidate,
            superseded=target.content,
        )
        self._backend.update_node(owner_id, node, vec)
        link_ids = self._form_semantic_links(owner_id, node, vec, re_eval=True)
        link_ids += self._attach_typed(owner_id, node.id, candidate)
        return MergeOutcome(
            action=MergeAction.EXTENDED,
            node_id=node.id,
            created_link_ids=tuple(link_ids),
            entity_ids=candidate.entity_ids,
        )

    # -- helpers ------------------------------------------------------------

    def _rebuilt(
        self,
        target: ConceptNode,
        *,
        content: str,
        candidate: KnowledgeCandidate,
        superseded: str | None = None,
    ) -> ConceptNode:
        """A fresh ConceptNode (same id, content_hash auto-recomputed) with the trail grown."""
        entry = candidate.provenance
        if superseded is not None:
            # Prior content preserved as STRUCTURED data (D-K0-4) — K4 trajectory / K5
            # before-after read it directly, not out of free-text.
            entry = entry.model_copy(update={"superseded_content": superseded})
        wellbeing = (
            candidate.wellbeing_category
            if candidate.wellbeing_category is not None
            else target.wellbeing_category
        )
        return ConceptNode(
            id=target.id,
            node_kind=target.node_kind,
            concept_name=target.concept_name,
            content=content,
            metadata=dict(target.metadata),
            wellbeing_category=wellbeing,
            provenance=(*target.provenance, entry),
            created_at=target.created_at,
        )

    def _attach_typed(
        self, owner_id: str, node_id: str, candidate: KnowledgeCandidate
    ) -> list[str]:
        """Record entity associations + attach K2's proposed typed links (T6b).

        Entity associations (``candidate.entity_ids``) go to the join table —
        ENTITY links are traversed on-the-fly through it, never materialised
        (D-K0-9 / the locked association model). Proposed temporal/causal links go
        to ``graph_edges`` (idempotent by edge id; K2 owns the conservative causal
        bar, D-K0-8). Self-targeting proposed links are skipped.
        """
        self._backend.associate_entities(owner_id, node_id, candidate.entity_ids)
        link_ids: list[str] = []
        for proposed in candidate.proposed_links:
            if proposed.target_node_id == node_id:
                continue
            edge = TypedLink(
                id=make_edge_id(node_id, proposed.target_node_id, proposed.link_type),
                src_node_id=node_id,
                dst_node_id=proposed.target_node_id,
                link_type=proposed.link_type,
                weight=proposed.weight,
                provenance=candidate.provenance,
                created_at=datetime.now(UTC),
            )
            self._backend.upsert_edge(owner_id, edge)
            link_ids.append(edge.id)
        return link_ids

    def _form_semantic_links(
        self, owner_id: str, node: ConceptNode, vec: Sequence[float], *, re_eval: bool
    ) -> list[str]:
        """Auto-wire the node to its nearest neighbours (D-K0-2).

        On extend (``re_eval``) the node's outgoing semantic edges are cleared and
        re-formed from the refreshed embedding, keeping the per-node cap honest.
        """
        if re_eval:
            self._backend.delete_links_from(owner_id, node.id, LinkType.SEMANTIC)
        # +1 because the node itself is in the result set (distance ~0) and skipped.
        neighbours = self._backend.dense_query(owner_id, vec, self._settings.max_semantic_links + 1)
        link_ids: list[str] = []
        for neighbour in neighbours:
            if neighbour.id == node.id:
                continue
            sim = _similarity(neighbour)
            if sim < self._settings.semantic_link_threshold:
                continue
            edge = TypedLink(
                id=make_edge_id(node.id, neighbour.id, LinkType.SEMANTIC),
                src_node_id=node.id,
                dst_node_id=neighbour.id,
                link_type=LinkType.SEMANTIC,
                weight=round(sim, 4),
                created_at=datetime.now(UTC),
            )
            self._backend.upsert_edge(owner_id, edge)
            link_ids.append(edge.id)
            if len(link_ids) >= self._settings.max_semantic_links:
                break
        return link_ids


def _similarity(node: ConceptNode) -> float:
    """Cosine similarity from a dense-query result's ``distance`` (1 - distance)."""
    return 1.0 - (node.distance if node.distance is not None else 1.0)

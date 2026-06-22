"""Hybrid retrieval over the knowledge graph — the K1 surface (Spec K1, T2/T3).

:class:`HybridRetriever` orchestrates K0's two read legs (dense, already
exact-reranked; sparse FTS) into one ranking via RRF (T2), then expands one
bounded type-aware hop along the typed links (T3). It is **pure orchestration**:
it calls the landed :class:`~persona.graph.protocol.GraphStore` contract as-is —
no re-rerank, no re-embed, no store fork. Synchronous (D-07-1; "parallel legs" =
architecturally independent, not concurrent).

**The allowlist seam (D-K1-7 / K1-R-5).** User isolation is already airtight in
K0 (RLS on the sparse leg + the in-kernel allowlist on the dense leg). The K4
*subtraction* (``allowlist = user_nodes − flagged``) is the one gap, because
``search_fts`` has no allowlist parameter — so a flagged node could surface via
the sparse leg. K1 closes it with a **post-fusion filter over the fused result**
(dense ∪ sparse ∪ traversal): isolation/safety, not relevance, so the §4
no-gating property is preserved. The per-leg over-fetch pools (``dense_pool`` /
``sparse_pool`` > ``result_budget``) keep the budget full after subtraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.graph.fusion import HybridResult, reciprocal_rank_fusion
from persona.graph.models import LinkType

if TYPE_CHECKING:
    from persona.graph.config import GraphSettings
    from persona.graph.protocol import GraphStore

__all__ = ["HybridRetriever"]


class HybridRetriever:
    """Query → hybrid-ranked nodes over the knowledge graph (Spec K1).

    Composes a :class:`~persona.graph.protocol.GraphStore` (the read legs) with
    :class:`~persona.graph.config.GraphSettings` (the tunables) by constructor
    injection. ``retrieve`` is a read — it never writes (CQS).
    """

    def __init__(self, store: GraphStore, settings: GraphSettings) -> None:
        """Inject the graph store (K0's read contract) and the graph settings."""
        self._store = store
        self._settings = settings

    def retrieve(
        self,
        owner_id: str,
        query: str,
        *,
        allowlist: set[str] | None = None,
        top_k: int | None = None,
    ) -> list[HybridResult]:
        """Return hybrid-ranked nodes for ``query``, within the result budget.

        Runs the dense and sparse legs independently over the same owner+allowlist
        scope, fuses them via weighted RRF (never gated — §4), applies the K4
        subtraction as a post-fusion filter over both legs (D-K1-7), expands one
        bounded type-aware hop over the top fused nodes (augment-never-displace),
        and truncates to the budget with contiguous final ranks.

        Args:
            owner_id: The user scope (the K0 ``owner_id`` first-parameter convention).
            query: The natural-language query.
            allowlist: The positive allowed node-id set (``user_nodes − flagged``
                for K4); ``None`` = the user's whole graph (no subtraction).
            top_k: Override the configured ``result_budget`` for this call.

        Returns:
            Up to the result budget of :class:`HybridResult`, fused-rank order
            (direct hits first, traversal neighbours appended at discounted rank).
        """
        settings = self._settings
        budget = top_k if top_k is not None else settings.result_budget

        dense = self._store.search_dense(owner_id, query, settings.dense_pool, allowlist=allowlist)
        sparse = self._store.search_fts(owner_id, query, settings.sparse_pool)

        fused = reciprocal_rank_fusion(
            dense=dense,
            sparse=sparse,
            rrf_k=settings.rrf_k,
            dense_weight=settings.dense_weight,
            sparse_weight=settings.sparse_weight,
            top_k=len(dense) + len(sparse),
        )

        core = self._apply_subtraction(fused, allowlist)
        expanded = self._expand(owner_id, core, allowlist, budget)
        return self._finalize(core + expanded, budget)

    # ----- helpers ---------------------------------------------------------

    def _apply_subtraction(
        self, results: list[HybridResult], allowlist: set[str] | None
    ) -> list[HybridResult]:
        """Drop any node outside the allowed set — the K4 subtraction (D-K1-7).

        ``None`` = the whole user graph (no subtraction); the dense leg already
        enforced an explicit allowlist in-kernel, so this closes the sparse-leg
        gap (and, later, traversal output) for a complete, query-independent
        subtraction. Isolation/safety only — never a relevance gate.
        """
        if allowlist is None:
            return results
        return [r for r in results if r.node.id in allowlist]

    def _finalize(self, results: list[HybridResult], budget: int) -> list[HybridResult]:
        """Truncate to the budget and renumber ``rank`` contiguously from 1."""
        return [
            r.model_copy(update={"rank": rank}) for rank, r in enumerate(results[:budget], start=1)
        ]

    def _expand(
        self,
        owner_id: str,
        core: list[HybridResult],
        allowlist: set[str] | None,
        budget: int,
    ) -> list[HybridResult]:
        """One bounded type-aware hop over the top fused nodes (D-K1-3).

        Expands the top ``traversal_seed_count`` fused nodes via ``neighbors``
        (per-node ``limit`` caps at the source), weights each neighbour by its
        link type × edge weight, dedupes against the core and across seeds, drops
        any node outside the K4-allowed set, and returns the highest-weighted up
        to the per-query ``traversal_budget`` and the remaining result-budget
        room (augment-never-displace). Returns ``[]`` when traversal is disabled
        or the budget is already filled by direct hits.
        """
        settings = self._settings
        remaining = budget - len(core)
        if settings.traversal_seed_count == 0 or settings.traversal_budget == 0 or remaining <= 0:
            return []

        seen = {r.node.id for r in core}
        scored: list[tuple[float, HybridResult]] = []
        for seed in core[: settings.traversal_seed_count]:
            for edge, node in self._store.neighbors(
                owner_id, seed.node.id, link_types=None, limit=settings.traversal_per_node
            ):
                if node.id in seen:
                    continue
                if allowlist is not None and node.id not in allowlist:
                    continue  # the K4 subtraction applies to traversal output too
                seen.add(node.id)
                weight = self._link_weight(edge.link_type) * (
                    edge.weight if edge.weight is not None else 1.0
                )
                scored.append(
                    (
                        weight,
                        HybridResult(
                            node=node,
                            score=0.0,  # traversal nodes are not RRF-scored
                            rank=0,  # renumbered in _finalize
                            via_traversal=True,
                            traversal_link_type=edge.link_type,
                        ),
                    )
                )

        # Highest weight first; stable sort keeps seed/edge order on ties.
        scored.sort(key=lambda item: -item[0])
        cap = min(settings.traversal_budget, remaining)
        return [result for _, result in scored[:cap]]

    def _link_weight(self, link_type: LinkType) -> float:
        """The configured expansion weight for a link type (D-K1-3)."""
        settings = self._settings
        weights = {
            LinkType.ENTITY: settings.traversal_weight_entity,
            LinkType.CAUSAL: settings.traversal_weight_causal,
            LinkType.TEMPORAL: settings.traversal_weight_temporal,
            LinkType.SEMANTIC: settings.traversal_weight_semantic,
        }
        return weights[link_type]

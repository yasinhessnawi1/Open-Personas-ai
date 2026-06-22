"""Reciprocal-rank fusion of the two retrieval legs (Spec K1, T1; D-K1-2/-4).

The architectural lock of hybrid retrieval (spec §4): the dense (semantic,
already exact-reranked by K0) and sparse (BM25/FTS) legs are fused **in parallel,
never gated**. Either signal alone can surface a node; both together rank it
highest. Fusion is **rank-based** (Reciprocal Rank Fusion, Cormack et al. SIGIR
2009) — cross-leg score scales (cosine ``distance`` vs ``ts_rank``) are
incomparable, so RRF crosses *rank*, not score, and needs no normalization.

Carried forward from Persona-RAG's ``reciprocal_rank_fusion`` and re-homed here:
**single-query** (not per-query batches), **weighted** per leg (D-K1-2), keyed on
:attr:`ConceptNode.id`. The K4 subtraction is NOT applied here (it is a
post-fusion filter in the retriever, D-K1-7) — fusion stays a pure, total
function over two ranked lists.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict

from persona.graph.models import ConceptNode, LinkType  # noqa: TC001 — Pydantic runtime

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = ["HybridResult", "reciprocal_rank_fusion"]


class HybridResult(BaseModel):
    """One hybrid-ranked node + why it was retrieved — the K3-facing contract (D-K1-4).

    K3 (graph-aware prompt construction) consumes a list of these; the per-leg
    provenance lets it order/label by *why* a node surfaced and makes the
    no-gating property observable (a ``sparse_rank is None`` node that still
    ranks is a dense-only paraphrase match that survived fusion — criterion 5).

    Attributes:
        node: The retrieved concept-node (the dense copy when present, so the
            dense ``distance`` is preserved for any score-level tiebreak K3 wants).
        score: The fused RRF score (Σ over legs of ``weight · 1/(rrf_k + rank)``).
        rank: The final 1-indexed position in the fused ranking.
        dense_rank: 1-indexed rank in the dense leg; ``None`` if the dense leg did
            not return this node.
        sparse_rank: 1-indexed rank in the sparse leg; ``None`` if the sparse leg
            did not return this node.
        via_traversal: ``True`` if this node entered via link-aware traversal
            (Spec K1, T3) rather than a retrieval leg.
        traversal_link_type: The link type the traversal followed to reach this
            node (set only when :attr:`via_traversal`); ``None`` otherwise.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    node: ConceptNode
    score: float
    rank: int
    dense_rank: int | None = None
    sparse_rank: int | None = None
    via_traversal: bool = False
    traversal_link_type: LinkType | None = None


def reciprocal_rank_fusion(
    *,
    dense: Sequence[ConceptNode],
    sparse: Sequence[ConceptNode],
    rrf_k: int,
    dense_weight: float,
    sparse_weight: float,
    top_k: int,
) -> list[HybridResult]:
    """Fuse the dense and sparse ranked lists into one ranking via weighted RRF.

    The fused score for a node is the weighted sum of its reciprocal ranks across
    the legs it appears in: ``Σ_leg weight_leg · 1/(rrf_k + rank_leg)`` (1-indexed
    rank). A node present in only one leg keeps that leg's single contribution —
    it is never gated out by absence from the other (the §4 no-gating property).
    Ties are broken by ``node.id`` ascending for a deterministic, stable order.

    When a node appears in both legs the **dense** node object is kept (it carries
    the dense ``distance`` populated by K0); a sparse-only node keeps its own.

    Args:
        dense: The dense leg's nodes, best-first (already exact-reranked by K0).
        sparse: The sparse (FTS/BM25) leg's nodes, best-first.
        rrf_k: The RRF constant (D-K1-2; default 60 lives in ``GraphSettings``).
        dense_weight: Per-leg weight on the dense contribution.
        sparse_weight: Per-leg weight on the sparse contribution.
        top_k: Maximum number of fused results to return (the result budget).

    Returns:
        Up to ``top_k`` :class:`HybridResult`, fused-score-descending.
    """
    dense_ranks = {node.id: rank for rank, node in enumerate(dense, start=1)}
    sparse_ranks = {node.id: rank for rank, node in enumerate(sparse, start=1)}

    # Node objects keyed by id; the dense copy wins (it carries `distance`).
    nodes: dict[str, ConceptNode] = {}
    for node in sparse:
        nodes.setdefault(node.id, node)
    for node in dense:
        nodes[node.id] = node

    scored: list[tuple[float, str]] = []
    for node_id in nodes:
        score = 0.0
        dense_rank = dense_ranks.get(node_id)
        if dense_rank is not None:
            score += dense_weight * (1.0 / (rrf_k + dense_rank))
        sparse_rank = sparse_ranks.get(node_id)
        if sparse_rank is not None:
            score += sparse_weight * (1.0 / (rrf_k + sparse_rank))
        scored.append((score, node_id))

    scored.sort(key=lambda item: (-item[0], item[1]))

    return [
        HybridResult(
            node=nodes[node_id],
            score=score,
            rank=rank,
            dense_rank=dense_ranks.get(node_id),
            sparse_rank=sparse_ranks.get(node_id),
        )
        for rank, (score, node_id) in enumerate(scored[:top_k], start=1)
    ]

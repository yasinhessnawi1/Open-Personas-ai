"""Unit tests for RRF fusion + the HybridResult shape (Spec K1, T1).

The architectural lock: parallel-not-gated fusion. These tests pin the no-gating
property (a node in only ONE leg still ranks — §4 / criterion 5), the
hybrid-justifies-itself property (a node in BOTH legs outranks single-leg nodes —
criterion 4), deterministic stable ordering, and the empty/disjoint edge cases —
all on synthetic ranked lists, no store.
"""

from __future__ import annotations

from datetime import UTC, datetime

from persona.graph.fusion import HybridResult, reciprocal_rank_fusion
from persona.graph.models import ConceptNode, NodeKind, NodeProvenance
from persona.schema.chunks import WriteSource

NOW = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)


def _node(node_id: str, *, distance: float | None = None) -> ConceptNode:
    return ConceptNode(
        id=node_id,
        node_kind=NodeKind.FACT,
        concept_name="c",
        content="c",
        distance=distance,
        provenance=(NodeProvenance(source=WriteSource.PERSONA_SELF, written_at=NOW),),
        created_at=NOW,
    )


def _ids(results: list[HybridResult]) -> list[str]:
    return [r.node.id for r in results]


# --- no-gating: a node present in ONLY one leg still ranks (criterion 5) -------


def test_dense_only_node_survives_fusion() -> None:
    # "a" appears only in the dense leg (the paraphrase-only match, zero lexical
    # overlap). It must NOT be gated out by its absence from the sparse leg.
    dense = [_node("a"), _node("b")]
    sparse = [_node("b"), _node("c")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert "a" in _ids(fused)


def test_sparse_only_node_survives_fusion() -> None:
    # The mirror: "c" appears only in the sparse leg (the exact-term match) and survives.
    dense = [_node("a"), _node("b")]
    sparse = [_node("b"), _node("c")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert "c" in _ids(fused)


def test_per_leg_provenance_makes_no_gating_observable() -> None:
    dense = [_node("a"), _node("b")]
    sparse = [_node("b"), _node("c")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    by_id = {r.node.id: r for r in fused}
    # a: dense-only → sparse_rank is None; c: sparse-only → dense_rank is None; b: both.
    assert by_id["a"].dense_rank == 1
    assert by_id["a"].sparse_rank is None
    assert by_id["c"].sparse_rank == 2
    assert by_id["c"].dense_rank is None
    assert by_id["b"].dense_rank == 2
    assert by_id["b"].sparse_rank == 1


# --- hybrid justifies itself: a both-legs node outranks single-leg nodes -------


def test_node_in_both_legs_outranks_single_leg_nodes() -> None:
    # "b" is mid-rank in both legs; "a"/"c" are top of one leg each. The summed
    # reciprocal-rank contribution must lift "b" above either lone-leg node.
    dense = [_node("a"), _node("b"), _node("x")]
    sparse = [_node("c"), _node("b"), _node("y")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    ranking = _ids(fused)
    assert ranking[0] == "b"
    assert ranking.index("b") < ranking.index("a")
    assert ranking.index("b") < ranking.index("c")


def test_weights_bias_the_favoured_leg() -> None:
    # Same single-leg top nodes; weighting sparse heavier lifts the sparse top.
    dense = [_node("d")]
    sparse = [_node("s")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=5.0, top_k=10
    )
    assert _ids(fused)[0] == "s"


# --- determinism / stability --------------------------------------------------


def test_ties_broken_by_node_id_for_stable_ordering() -> None:
    # Symmetric single-leg top nodes have equal fused score → id ascending.
    dense = [_node("zeta")]
    sparse = [_node("alpha")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert _ids(fused) == ["alpha", "zeta"]


def test_final_rank_is_dense_one_indexed_and_contiguous() -> None:
    dense = [_node("a"), _node("b")]
    sparse = [_node("c")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert [r.rank for r in fused] == [1, 2, 3]


def test_score_is_sum_of_weighted_reciprocal_ranks() -> None:
    dense = [_node("a"), _node("b")]
    sparse = [_node("b")]  # b: dense rank 2, sparse rank 1
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    by_id = {r.node.id: r for r in fused}
    assert by_id["b"].score == (1.0 / (60 + 2)) + (1.0 / (60 + 1))
    assert by_id["a"].score == 1.0 / (60 + 1)


def test_dense_node_object_wins_so_distance_is_preserved() -> None:
    # The dense leg populates `distance`; when a node is in both legs the fused
    # result must carry the dense copy (with distance), not the sparse one.
    dense = [_node("b", distance=0.12)]
    sparse = [_node("b")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert fused[0].node.distance == 0.12


# --- edge cases ---------------------------------------------------------------


def test_empty_dense_leg_returns_sparse_in_order() -> None:
    sparse = [_node("a"), _node("b")]
    fused = reciprocal_rank_fusion(
        dense=[], sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert _ids(fused) == ["a", "b"]


def test_empty_sparse_leg_returns_dense_in_order() -> None:
    dense = [_node("a"), _node("b")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=[], rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert _ids(fused) == ["a", "b"]


def test_both_legs_empty_returns_empty() -> None:
    fused = reciprocal_rank_fusion(
        dense=[], sparse=[], rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert fused == []


def test_disjoint_legs_keep_all_nodes() -> None:
    dense = [_node("a"), _node("b")]
    sparse = [_node("c"), _node("d")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=sparse, rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=10
    )
    assert set(_ids(fused)) == {"a", "b", "c", "d"}


def test_top_k_truncates_to_budget() -> None:
    dense = [_node("a"), _node("b"), _node("c"), _node("d")]
    fused = reciprocal_rank_fusion(
        dense=dense, sparse=[], rrf_k=60, dense_weight=1.0, sparse_weight=1.0, top_k=2
    )
    assert _ids(fused) == ["a", "b"]


def test_hybrid_result_is_frozen_and_forbids_extra() -> None:
    import pytest
    from pydantic import ValidationError

    r = HybridResult(node=_node("a"), score=0.5, rank=1, dense_rank=1, sparse_rank=None)
    with pytest.raises(ValidationError):
        HybridResult(  # type: ignore[call-arg]
            node=_node("a"), score=0.5, rank=1, dense_rank=1, sparse_rank=None, bogus=1
        )
    with pytest.raises(ValidationError):
        r.score = 0.9  # type: ignore[misc]

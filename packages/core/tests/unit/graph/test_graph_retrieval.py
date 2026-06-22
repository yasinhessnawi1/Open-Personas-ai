"""Unit tests for HybridRetriever orchestration (Spec K1, T2/T3).

Fakes the GraphStore (the K0 read legs are tested in K0) so the retriever's own
responsibilities are isolated: both legs invoked with identical scope, RRF
fusion, the K4 post-fusion subtraction over BOTH legs (D-K1-7), budget
truncation + contiguous re-rank, and CQS (retrieve reads, never writes). Task 3
adds the traversal cases.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from persona.graph.config import GraphSettings
from persona.graph.models import ConceptNode, LinkType, NodeKind, NodeProvenance, TypedLink
from persona.graph.retrieval import HybridRetriever
from persona.schema.chunks import WriteSource

NOW = datetime(2026, 6, 22, 12, 0, tzinfo=UTC)
OWNER = "user-1"


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


class _FakeStore:
    """Records leg calls and returns canned ranked lists (duck-typed GraphStore)."""

    def __init__(
        self,
        *,
        dense: list[ConceptNode] | None = None,
        sparse: list[ConceptNode] | None = None,
        neighbors: list[tuple[TypedLink, ConceptNode]] | None = None,
    ) -> None:
        self._dense = dense or []
        self._sparse = sparse or []
        self._neighbors = neighbors or []
        self.dense_calls: list[tuple[str, str, int, set[str] | None]] = []
        self.sparse_calls: list[tuple[str, str, int]] = []
        self.neighbor_calls: list[tuple[str, str, set[LinkType] | None, int]] = []

    def search_dense(
        self,
        owner_id: str,
        query: str,
        top_k: int,
        *,
        allowlist: set[str] | None = None,
    ) -> list[ConceptNode]:
        self.dense_calls.append((owner_id, query, top_k, allowlist))
        # Honour the in-kernel allowlist the way K0 does (scope the dense leg).
        if allowlist is not None:
            return [n for n in self._dense if n.id in allowlist][:top_k]
        return self._dense[:top_k]

    def search_fts(self, owner_id: str, query: str, top_k: int) -> list[ConceptNode]:
        self.sparse_calls.append((owner_id, query, top_k))
        return self._sparse[:top_k]  # RLS-scoped only; NO allowlist (the K0 reality)

    def neighbors(
        self,
        owner_id: str,
        node_id: str,
        *,
        link_types: set[LinkType] | None = None,
        limit: int,
    ) -> list[tuple[TypedLink, ConceptNode]]:
        self.neighbor_calls.append((owner_id, node_id, link_types, limit))
        return self._neighbors[:limit]


def _retriever(store: _FakeStore, **overrides: object) -> HybridRetriever:
    settings = GraphSettings(**overrides)  # type: ignore[arg-type]
    return HybridRetriever(store, settings)  # type: ignore[arg-type]


# --- both legs run over identical scope ---------------------------------------


def test_both_legs_invoked_with_same_owner_and_query() -> None:
    store = _FakeStore(dense=[_node("a")], sparse=[_node("b")])
    _retriever(store).retrieve(OWNER, "q")
    assert store.dense_calls[0][:2] == (OWNER, "q")
    assert store.sparse_calls[0][:2] == (OWNER, "q")


def test_legs_use_configured_over_fetch_pools() -> None:
    store = _FakeStore()
    _retriever(store, dense_pool=33, sparse_pool=44).retrieve(OWNER, "q")
    assert store.dense_calls[0][2] == 33
    assert store.sparse_calls[0][2] == 44


def test_allowlist_passed_to_dense_in_kernel() -> None:
    store = _FakeStore(dense=[_node("a")], sparse=[])
    allow = {"a", "b"}
    _retriever(store).retrieve(OWNER, "q", allowlist=allow)
    assert store.dense_calls[0][3] == allow


# --- no-gating survives the full path (criterion 5) ---------------------------


def test_paraphrase_only_dense_match_survives_retrieval() -> None:
    # "para" is dense-only (zero lexical overlap) — it must appear in the output.
    store = _FakeStore(dense=[_node("para"), _node("shared")], sparse=[_node("shared")])
    out = store_ids(_retriever(store).retrieve(OWNER, "q"))
    assert "para" in out


# --- K4 post-fusion subtraction over BOTH legs (criterion 6 / D-K1-7) ---------


def test_k4_subtraction_removes_flagged_node_from_sparse_leg() -> None:
    # "flagged" is excluded in-kernel from dense (allowlist), but the sparse leg
    # has no allowlist — without the post-fusion filter it would leak. It must not.
    store = _FakeStore(dense=[_node("ok")], sparse=[_node("ok"), _node("flagged")])
    allow = {"ok"}  # user_nodes − {flagged}
    out = store_ids(_retriever(store).retrieve(OWNER, "q", allowlist=allow))
    assert "flagged" not in out
    assert "ok" in out


def test_k4_subtraction_no_effect_on_the_rest() -> None:
    store = _FakeStore(dense=[_node("a"), _node("b")], sparse=[_node("b"), _node("flagged")])
    allow = {"a", "b"}
    out = store_ids(_retriever(store).retrieve(OWNER, "q", allowlist=allow))
    assert set(out) == {"a", "b"}


def test_none_allowlist_applies_no_subtraction() -> None:
    store = _FakeStore(dense=[_node("a")], sparse=[_node("b")])
    out = store_ids(_retriever(store).retrieve(OWNER, "q", allowlist=None))
    assert set(out) == {"a", "b"}


def test_empty_allowed_set_returns_empty() -> None:
    store = _FakeStore(dense=[], sparse=[_node("flagged")])
    out = _retriever(store).retrieve(OWNER, "q", allowlist=set())
    assert out == []


# --- budget truncation + contiguous re-rank -----------------------------------


def test_budget_truncates_and_reranks_contiguously() -> None:
    store = _FakeStore(dense=[_node("a"), _node("b"), _node("c"), _node("d")], sparse=[])
    out = _retriever(store, result_budget=2).retrieve(OWNER, "q")
    assert [r.node.id for r in out] == ["a", "b"]
    assert [r.rank for r in out] == [1, 2]


def test_top_k_override_beats_configured_budget() -> None:
    store = _FakeStore(dense=[_node("a"), _node("b"), _node("c")], sparse=[])
    out = _retriever(store, result_budget=10).retrieve(OWNER, "q", top_k=1)
    assert [r.node.id for r in out] == ["a"]


def test_per_leg_provenance_preserved_through_retrieval() -> None:
    store = _FakeStore(dense=[_node("a"), _node("shared")], sparse=[_node("shared")])
    out = {r.node.id: r for r in _retriever(store).retrieve(OWNER, "q")}
    assert out["a"].sparse_rank is None  # dense-only
    assert out["shared"].dense_rank is not None
    assert out["shared"].sparse_rank is not None


# --- config guard (the folded-in nit) -----------------------------------------


def test_both_weights_zero_is_rejected() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        GraphSettings(dense_weight=0.0, sparse_weight=0.0)


def store_ids(results: list) -> list[str]:  # noqa: ANN401 — test helper over HybridResult
    return [r.node.id for r in results]


# ===== Task 3: link-aware traversal ==========================================


def _link(src: str, dst: str, link_type: LinkType, weight: float | None = None) -> TypedLink:
    return TypedLink(
        id=f"{src}::{link_type}::{dst}",
        src_node_id=src,
        dst_node_id=dst,
        link_type=link_type,
        weight=weight,
        created_at=NOW,
    )


def test_traversal_surfaces_entity_thread_the_flat_query_missed() -> None:
    # "seed" is the direct hit; "thread" is its entity neighbour, in neither leg.
    nbrs = [(_link("seed", "thread", LinkType.ENTITY), _node("thread"))]
    store = _FakeStore(dense=[_node("seed")], sparse=[], neighbors=nbrs)
    out = _retriever(store).retrieve(OWNER, "q")
    by_id = {r.node.id: r for r in out}
    assert "thread" in by_id
    assert by_id["thread"].via_traversal is True
    assert by_id["thread"].traversal_link_type is LinkType.ENTITY


def test_traversal_neighbours_appended_after_the_fused_core() -> None:
    nbrs = [(_link("seed", "thread", LinkType.ENTITY), _node("thread"))]
    store = _FakeStore(dense=[_node("seed")], sparse=[], neighbors=nbrs)
    out = _retriever(store).retrieve(OWNER, "q")
    assert [r.node.id for r in out] == ["seed", "thread"]
    assert out[0].via_traversal is False
    assert out[1].via_traversal is True


def test_link_type_weighting_orders_expansions_entity_over_semantic() -> None:
    # Provide semantic FIRST to prove the weight sort actually reorders.
    nbrs = [
        (_link("seed", "sem", LinkType.SEMANTIC), _node("sem")),
        (_link("seed", "ent", LinkType.ENTITY), _node("ent")),
    ]
    store = _FakeStore(dense=[_node("seed")], sparse=[], neighbors=nbrs)
    out = [r.node.id for r in _retriever(store).retrieve(OWNER, "q")]
    assert out.index("ent") < out.index("sem")  # ENTITY (1.0) before SEMANTIC (0.4)


def test_traversal_two_level_cap_prevents_flooding() -> None:
    # 20 candidate neighbours; per-node limit caps at the source (fake slices by
    # limit), the per-query budget caps the total — together no flooding.
    nbrs = [(_link("seed", f"n{i}", LinkType.SEMANTIC), _node(f"n{i}")) for i in range(20)]
    store = _FakeStore(dense=[_node("seed")], sparse=[], neighbors=nbrs)
    out = _retriever(store, traversal_per_node=5, traversal_budget=2, result_budget=50).retrieve(
        OWNER, "q"
    )
    traversal = [r for r in out if r.via_traversal]
    assert len(traversal) == 2  # min(per_node_pool=5, traversal_budget=2)
    assert store.neighbor_calls[0][3] == 5  # per-node limit passed to the source


def test_traversal_dedupes_neighbour_already_in_core() -> None:
    # "dup" is a direct hit AND a neighbour — it must appear once, as the core hit.
    nbrs = [(_link("seed", "dup", LinkType.ENTITY), _node("dup"))]
    store = _FakeStore(dense=[_node("seed"), _node("dup")], sparse=[], neighbors=nbrs)
    out = _retriever(store).retrieve(OWNER, "q")
    dup = [r for r in out if r.node.id == "dup"]
    assert len(dup) == 1
    assert dup[0].via_traversal is False


def test_k4_subtraction_applies_to_traversal_output() -> None:
    nbrs = [(_link("seed", "flagged", LinkType.ENTITY), _node("flagged"))]
    store = _FakeStore(dense=[_node("seed")], sparse=[], neighbors=nbrs)
    out = store_ids(_retriever(store).retrieve(OWNER, "q", allowlist={"seed"}))
    assert "flagged" not in out
    assert out == ["seed"]


def test_traversal_disabled_when_seed_count_zero() -> None:
    nbrs = [(_link("seed", "thread", LinkType.ENTITY), _node("thread"))]
    store = _FakeStore(dense=[_node("seed")], sparse=[], neighbors=nbrs)
    out = _retriever(store, traversal_seed_count=0).retrieve(OWNER, "q")
    assert store_ids(out) == ["seed"]
    assert store.neighbor_calls == []


def test_traversal_never_displaces_a_direct_hit() -> None:
    # Budget is full of direct hits → traversal adds nothing (augment-never-displace),
    # and we don't even call the store (remaining <= 0 short-circuit).
    nbrs = [(_link("a", "thread", LinkType.ENTITY), _node("thread"))]
    store = _FakeStore(dense=[_node("a")], sparse=[], neighbors=nbrs)
    out = _retriever(store, result_budget=1).retrieve(OWNER, "q")
    assert store_ids(out) == ["a"]
    assert store.neighbor_calls == []

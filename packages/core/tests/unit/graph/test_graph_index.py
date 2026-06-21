"""Unit tests for the dense-index layer (Spec K0, T7).

``exact_rerank`` and the factory need no DB and no turbovec. The turbovec adapter
tests ``importorskip`` turbovec and use an in-memory ``float32_fetch`` so the
mandatory rerank + allowlist + lifecycle are exercised without Postgres.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, cast

import pytest
from persona.graph.config import GraphSettings
from persona.graph.errors import GraphIndexError
from persona.graph.index import make_graph_index
from persona.graph.index_pgvector import PgvectorGraphIndex
from persona.graph.index_turbovec import exact_rerank
from persona.graph.protocol import GraphIndex

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Engine

DIM = 8


def _vec(primary: int, val: float = 1.0) -> list[float]:
    v = [0.0] * DIM
    v[primary] = val
    return v


def _mix(cos: float) -> list[float]:
    """A unit vector with cosine ``cos`` to ``_vec(0)`` (graded similarity).

    Note ``_vec(0, 0.5)`` is PARALLEL to ``_vec(0)`` (cosine ignores magnitude →
    1.0); graded similarity needs a second axis, which this provides.
    """
    v = [0.0] * DIM
    v[0] = cos
    v[1] = math.sqrt(max(0.0, 1.0 - cos * cos))
    return v


# ----- exact_rerank (pure) -------------------------------------------------


def test_exact_rerank_orders_by_float32_cosine() -> None:
    # ANN candidate order is deliberately wrong; rerank must fix it by float32.
    query = _vec(0)
    f32 = {1: _vec(0), 2: _mix(0.7), 3: _vec(1)}  # 1 nearest (cos 1), 2 mid (0.7), 3 orthogonal
    out = exact_rerank([3, 2, 1], query, f32, top_k=2)
    assert [s for s, _ in out] == [1, 2]
    assert out[0][1] > out[1][1]


def test_exact_rerank_drops_candidates_without_float32() -> None:
    out = exact_rerank([1, 99], _vec(0), {1: _vec(0)}, top_k=5)
    assert [s for s, _ in out] == [1]


# ----- factory -------------------------------------------------------------


def test_factory_defaults_to_pgvector() -> None:
    idx = make_graph_index(settings=GraphSettings(), engine=cast("Engine", object()))
    assert isinstance(idx, PgvectorGraphIndex)
    assert isinstance(idx, GraphIndex)


def test_factory_turbovec_requires_float32_fetch() -> None:
    settings = GraphSettings(index_backend="turbovec")
    with pytest.raises(GraphIndexError, match="requires float32_fetch"):
        make_graph_index(settings=settings, engine=cast("Engine", object()))


def test_factory_builds_turbovec_when_selected() -> None:
    pytest.importorskip("turbovec")
    from persona.graph.index_turbovec import TurbovecGraphIndex

    settings = GraphSettings(index_backend="turbovec", index_bit_width=4)
    idx = make_graph_index(
        settings=settings,
        engine=cast("Engine", object()),
        float32_fetch=lambda _s: {},
    )
    assert isinstance(idx, TurbovecGraphIndex)
    assert isinstance(idx, GraphIndex)


# ----- turbovec adapter (mandatory rerank, allowlist, lifecycle) -----------


@pytest.fixture
def turbo() -> tuple[GraphIndex, dict[int, list[float]]]:
    pytest.importorskip("turbovec")
    from persona.graph.index_turbovec import TurbovecGraphIndex

    store: dict[int, list[float]] = {}

    def fetch(surrogates: Sequence[int]) -> dict[int, list[float]]:
        return {s: store[s] for s in surrogates if s in store}

    idx = TurbovecGraphIndex(float32_fetch=fetch, dim=DIM, bit_width=4, rerank_n=50)
    return idx, store


def _add(
    idx: GraphIndex, store: dict[int, list[float]], surrogate: int, vector: list[float]
) -> None:
    store[surrogate] = vector
    idx.add(surrogate=surrogate, vector=vector)


def test_turbovec_add_search_with_mandatory_rerank(
    turbo: tuple[GraphIndex, dict[int, list[float]]],
) -> None:
    idx, store = turbo
    _add(idx, store, 1, _vec(0))
    _add(idx, store, 2, _vec(1))  # orthogonal
    _add(idx, store, 3, _mix(0.7))  # mid similarity
    out = idx.search(query_vector=_vec(0), top_k=2)
    # float32-exact final order: surrogate 1 (cos 1) then 3 (cos 0.7), not 2 (cos 0).
    assert [s for s, _ in out] == [1, 3]


def test_turbovec_allowlist_restricts_in_kernel(
    turbo: tuple[GraphIndex, dict[int, list[float]]],
) -> None:
    idx, store = turbo
    _add(idx, store, 1, _vec(0))
    _add(idx, store, 2, _vec(0, 0.9))
    out = idx.search(query_vector=_vec(0), top_k=5, allowlist=[2])
    assert [s for s, _ in out] == [2]  # 1 excluded by the allowlist


def test_turbovec_empty_allowlist_returns_nothing(
    turbo: tuple[GraphIndex, dict[int, list[float]]],
) -> None:
    idx, store = turbo
    _add(idx, store, 1, _vec(0))
    assert idx.search(query_vector=_vec(0), top_k=5, allowlist=[]) == []


def test_turbovec_remove_replace_contains(
    turbo: tuple[GraphIndex, dict[int, list[float]]],
) -> None:
    idx, store = turbo
    _add(idx, store, 1, _vec(0))
    assert idx.contains(1)
    idx.replace(surrogate=1, vector=_vec(1))
    store[1] = _vec(1)
    assert idx.search(query_vector=_vec(1), top_k=1)[0][0] == 1
    assert idx.remove(1) is True
    assert not idx.contains(1)
    assert idx.remove(1) is False


def test_turbovec_rebuild_from_items(turbo: tuple[GraphIndex, dict[int, list[float]]]) -> None:
    idx, store = turbo
    store.update({1: _vec(0), 2: _vec(1)})
    idx.rebuild([(1, _vec(0)), (2, _vec(1))])
    assert idx.contains(1)
    assert [s for s, _ in idx.search(query_vector=_vec(1), top_k=1)] == [2]


def test_turbovec_dim_mismatch_raises(turbo: tuple[GraphIndex, dict[int, list[float]]]) -> None:
    idx, _store = turbo
    with pytest.raises(GraphIndexError, match="dimension mismatch"):
        idx.add(surrogate=1, vector=[0.0, 1.0])

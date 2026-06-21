"""Unit tests for the K0 graph domain exceptions (T1)."""

from __future__ import annotations

import pytest
from persona.errors import PersonaError
from persona.graph.errors import (
    EntityResolutionError,
    GraphError,
    GraphIndexError,
    GraphRebuildError,
    NodeMergeError,
)

LEAVES = [EntityResolutionError, NodeMergeError, GraphIndexError, GraphRebuildError]


@pytest.mark.parametrize("exc", LEAVES)
def test_leaf_errors_subclass_graph_error_and_persona_error(exc: type[GraphError]) -> None:
    assert issubclass(exc, GraphError)
    assert issubclass(exc, PersonaError)


def test_graph_error_subclasses_persona_error() -> None:
    assert issubclass(GraphError, PersonaError)


@pytest.mark.parametrize("exc", LEAVES)
def test_leaf_errors_carry_structured_context(exc: type[GraphError]) -> None:
    err = exc("boom", context={"node_id": "u1::node::00000001", "backend": "pgvector"})
    assert err.context == {"node_id": "u1::node::00000001", "backend": "pgvector"}
    assert "node_id=u1::node::00000001" in str(err)
    assert str(err).startswith("boom [")


def test_graph_errors_are_catchable_as_graph_error() -> None:
    with pytest.raises(GraphError):
        raise NodeMergeError("cannot merge", context={"step": "extend"})


def test_graph_errors_are_catchable_as_persona_error() -> None:
    with pytest.raises(PersonaError):
        raise GraphIndexError("index out of sync", context={"surrogate": "7"})

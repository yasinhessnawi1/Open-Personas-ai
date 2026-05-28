"""Unit tests for PostgresBackend's pure-function helpers (spec 07, T05).

No database here — these cover the row<->chunk materialisation and the dim
assertion in isolation. The behavioural DB round-trip lives in the api
integration suite (T07).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from persona.schema.chunks import ChunkProvenance, PersonaChunk, WriteSource
from persona.stores.backend import Backend
from persona.stores.postgres import (
    EMBEDDING_DIM,
    PostgresBackend,
    _as_str_dict,
    _as_utc,
)

UTC_NOW = datetime(2026, 5, 28, 12, 0, 0, tzinfo=UTC)


class _DimEmbedder:
    """Embedder returning a fixed-length vector; length is configurable."""

    model_name = "dim-test"

    def __init__(self, dim: int) -> None:
        self._dim = dim

    @property
    def dimension(self) -> int:
        return self._dim

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * self._dim for _ in texts]


def _chunk(*, with_prov: bool = True) -> PersonaChunk:
    prov = (
        ChunkProvenance(
            source=WriteSource.USER,
            logical_id="lg1",
            version=2,
            superseded_by=None,
            written_at=UTC_NOW,
            written_by="user-1",
            reason="because",
        )
        if with_prov
        else None
    )
    return PersonaChunk(
        id="p1::self_facts::0001",
        text="I like tea.",
        metadata={"confidence": "0.9"},
        created_at=UTC_NOW,
        provenance=prov,
    )


def test_postgres_backend_satisfies_backend_protocol() -> None:
    class _Eng:  # minimal stand-in; never used (no DB call in this test)
        pass

    backend = PostgresBackend(engine=_Eng(), embedder=_DimEmbedder(EMBEDDING_DIM))  # type: ignore[arg-type]
    assert isinstance(backend, Backend)


def test_chunk_to_row_maps_provenance_to_columns() -> None:
    backend = PostgresBackend(engine=object(), embedder=_DimEmbedder(EMBEDDING_DIM))  # type: ignore[arg-type]
    row = backend._chunk_to_row("p1", "self_facts", _chunk(), [0.0] * EMBEDDING_DIM)
    assert row["logical_id"] == "lg1"
    assert row["version"] == 2
    assert row["prov_source"] == "user"
    assert row["written_by"] == "user-1"
    assert row["metadata"] == {"confidence": "0.9"}
    assert row["embedding_model"] == "bge-small-en-v1.5"


def test_chunk_to_row_identity_has_null_provenance() -> None:
    backend = PostgresBackend(engine=object(), embedder=_DimEmbedder(EMBEDDING_DIM))  # type: ignore[arg-type]
    row = backend._chunk_to_row("p1", "identity", _chunk(with_prov=False), [0.0] * EMBEDDING_DIM)
    assert row["logical_id"] is None
    assert row["prov_source"] is None
    assert row["version"] is None


def test_row_to_chunk_round_trips_provenance() -> None:
    backend = PostgresBackend(engine=object(), embedder=_DimEmbedder(EMBEDDING_DIM))  # type: ignore[arg-type]
    original = _chunk()
    row = backend._chunk_to_row("p1", "self_facts", original, [0.0] * EMBEDDING_DIM)
    restored = backend._row_to_chunk(row, distance=0.25)
    assert restored.id == original.id
    assert restored.provenance is not None
    assert restored.provenance.logical_id == "lg1"
    assert restored.provenance.version == 2
    assert restored.provenance.source is WriteSource.USER
    assert restored.distance == 0.25
    assert restored.metadata == {"confidence": "0.9"}


def test_upsert_rejects_wrong_dim_embedding() -> None:
    # The embedder yields a 16-dim vector; the column is 384 → fail fast.
    backend = PostgresBackend(engine=object(), embedder=_DimEmbedder(16))  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="embedding dim 16 != expected 384"):
        backend.upsert(persona_id="p1", store_kind="self_facts", chunks=[_chunk()])


def test_as_utc_attaches_and_converts() -> None:
    naive = datetime(2026, 5, 28, 12, 0, 0)  # noqa: DTZ001 — deliberately naive for the test
    assert _as_utc(naive).tzinfo is UTC


def test_as_str_dict_handles_none_and_json_string() -> None:
    assert _as_str_dict(None) == {}
    assert _as_str_dict({"a": 1}) == {"a": "1"}
    assert _as_str_dict('{"b": 2}') == {"b": "2"}

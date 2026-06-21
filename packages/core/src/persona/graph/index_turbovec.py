"""turbovec dense-index adapter — quantized in-RAM, MANDATORY exact-rerank (Spec K0, T7).

The OPT-IN dense index (D-K0-6): a quantized in-RAM ``turbovec.IdMapIndex`` keyed by
``uint64`` surrogate, with kernel-level allowlist filtering. **Never a hard
dependency** — turbovec is lazy-imported (behind the ``[turbovec]`` extra); a
missing install raises a clear ``GraphIndexError`` with an install hint, and the
default ``pgvector`` path needs none of this.

**The exact-rerank is structural, not a toggle (D-K0-7).** ``search`` runs ANN to a
wide top-N, then reranks those candidates against their **float32 truth** (fetched
via the injected ``float32_fetch`` — backed by Postgres) and returns the exact
top-k. There is no constructor flag to skip it: you cannot obtain a raw quantized
ranking from this adapter. So 4-bit is a memory/speed choice; the 0.95 recall gate
holds because the final ranking is float32-exact (the spec's whole thesis).
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np  # always present (sentence-transformers dep); turbovec stays lazy

from persona.graph.errors import GraphIndexError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Sequence

__all__ = ["TurbovecGraphIndex", "exact_rerank"]


def _cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0.0 or nb == 0.0 else dot / (na * nb)


def exact_rerank(
    candidates: Sequence[int],
    query_vector: Sequence[float],
    float32_by_surrogate: dict[int, list[float]],
    top_k: int,
) -> list[tuple[int, float]]:
    """Rerank ANN ``candidates`` by exact float32 cosine; return top-k ``(surrogate, score)``.

    The precision-recovery step (D-K0-7): quantized ANN picks the candidate set,
    float32 decides the final order. Candidates with no float32 vector available
    are dropped (defensive). Ordering is by exact cosine, descending.
    """
    scored = [
        (surr, _cosine(query_vector, float32_by_surrogate[surr]))
        for surr in candidates
        if surr in float32_by_surrogate
    ]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:top_k]


def _import_turbovec() -> object:
    try:
        import turbovec  # noqa: PLC0415 — lazy: turbovec is an optional extra
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise GraphIndexError(
            "turbovec is not installed",
            context={"backend": "turbovec", "install_hint": "pip install persona-core[turbovec]"},
        ) from exc
    return turbovec


class TurbovecGraphIndex:
    """Quantized in-RAM dense index with mandatory exact-rerank (implements ``GraphIndex``).

    Args:
        float32_fetch: Returns the durable float32 embeddings for a set of
            surrogates (Postgres-backed in production) — REQUIRED, because the
            rerank is mandatory. The adapter holds no float32 itself (that is the
            whole point of the quantized index).
        dim / bit_width: embedding dim (384) and quantization width (4-bit, D-K0-7).
        rerank_n: how many ANN candidates to rerank (≥ top_k; lean generous —
            rerank is a few dozen dot products).
        path: optional ``.tvim`` file; loaded if present, written by :meth:`persist`.
    """

    def __init__(
        self,
        *,
        float32_fetch: Callable[[Sequence[int]], dict[int, list[float]]],
        dim: int = 384,
        bit_width: int = 4,
        rerank_n: int = 50,
        path: str | None = None,
    ) -> None:
        self._tv = _import_turbovec()
        self._fetch = float32_fetch
        self._dim = dim
        self._bit_width = bit_width
        self._rerank_n = rerank_n
        self._path = path
        self._idx = self._new_index()
        if path is not None:
            self._maybe_load(path)

    def _new_index(self) -> object:
        return self._tv.IdMapIndex(dim=self._dim, bit_width=self._bit_width)  # type: ignore[attr-defined]

    def _maybe_load(self, path: str) -> None:
        from pathlib import Path

        if Path(path).exists():
            self._idx = self._tv.IdMapIndex.load(path)  # type: ignore[attr-defined]

    # -- mutate -------------------------------------------------------------

    def add(self, *, surrogate: int, vector: Sequence[float]) -> None:
        self._add_many([(surrogate, vector)])

    def replace(self, *, surrogate: int, vector: Sequence[float]) -> None:
        # turbovec has no upsert (D-K0-6 / research §6): remove-then-add.
        self._idx.remove(surrogate)  # type: ignore[attr-defined]
        self._add_many([(surrogate, vector)])

    def remove(self, surrogate: int) -> bool:
        return bool(self._idx.remove(surrogate))  # type: ignore[attr-defined]

    def contains(self, surrogate: int) -> bool:
        return bool(self._idx.contains(surrogate))  # type: ignore[attr-defined]

    def rebuild(self, items: Iterable[tuple[int, Sequence[float]]]) -> None:
        self._idx = self._new_index()
        self._add_many(list(items))

    def persist(self) -> None:
        if self._path is not None:
            self._idx.write(self._path)  # type: ignore[attr-defined]

    def _add_many(self, items: list[tuple[int, Sequence[float]]]) -> None:
        if not items:
            return
        vectors = np.asarray([list(v) for _, v in items], dtype=np.float32)
        if vectors.shape[1] != self._dim:
            raise GraphIndexError(
                "embedding dimension mismatch",
                context={"expected": str(self._dim), "got": str(vectors.shape[1])},
            )
        ids = np.asarray([s for s, _ in items], dtype=np.uint64)
        try:
            self._idx.add_with_ids(vectors, ids)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 - re-raise turbovec errors as domain
            raise GraphIndexError(
                "turbovec add failed", context={"count": str(len(items))}
            ) from exc

    # -- search (ANN → mandatory exact-rerank) ------------------------------

    def search(
        self,
        *,
        query_vector: Sequence[float],
        top_k: int,
        allowlist: Sequence[int] | None = None,
    ) -> list[tuple[int, float]]:
        if allowlist is not None and len(allowlist) == 0:
            return []
        q = np.asarray([list(query_vector)], dtype=np.float32)
        allow = None if allowlist is None else np.asarray(list(allowlist), dtype=np.uint64)
        # Over-fetch ANN candidates, then rerank against float32 (mandatory).
        n = max(self._rerank_n, top_k)
        _scores, ids = self._idx.search(q, n, allowlist=allow)  # type: ignore[attr-defined]
        candidates = [int(s) for s in ids[0]]
        if not candidates:
            return []
        float32 = self._fetch(candidates)
        return exact_rerank(candidates, query_vector, float32, top_k)

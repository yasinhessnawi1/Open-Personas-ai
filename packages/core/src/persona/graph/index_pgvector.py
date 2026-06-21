"""pgvector dense-index adapter — the DEFAULT + only-wired-prod path (Spec K0, T7).

For pgvector "the index IS Postgres": the float32 embeddings already live in
``graph_nodes`` (the transport writes them at merge), so this adapter stores
nothing of its own. ``add`` / ``replace`` / ``remove`` / ``rebuild`` / ``persist``
are **no-ops** (the transport + the table are the source of truth); ``search`` runs
exact pgvector cosine over ``graph_nodes`` restricted to the surrogate allowlist —
**identical allowlist semantics** to the turbovec adapter (here: ``WHERE surrogate
= ANY(allowlist)``, plus RLS's ``owner_id`` GUC in prod). Exact float32 search →
no rerank needed (the turbovec adapter reranks to reach the same exactness).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from persona.graph._schema import graph_nodes

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from sqlalchemy import Engine

__all__ = ["PgvectorGraphIndex"]


class PgvectorGraphIndex:
    """Exact pgvector dense index over ``graph_nodes`` (implements ``GraphIndex``).

    Owner-agnostic by design (the locked "one shared index + per-user allowlist"
    model): scoping is the allowlist (the user's surrogate set, computed by the
    store) plus Postgres RLS. The mutating methods are no-ops because the embeddings
    are maintained in ``graph_nodes`` by the transport — there is no separate index.
    """

    def __init__(self, *, engine: Engine) -> None:
        self._engine = engine

    # -- mutate (no-ops: the table IS the index) ----------------------------

    def add(self, *, surrogate: int, vector: Sequence[float]) -> None:  # noqa: ARG002
        return

    def replace(self, *, surrogate: int, vector: Sequence[float]) -> None:  # noqa: ARG002
        return

    def remove(self, surrogate: int) -> bool:  # noqa: ARG002
        # The transport's delete_node removes the row; nothing to do here.
        return True

    def rebuild(self, items: Iterable[tuple[int, Sequence[float]]]) -> None:  # noqa: ARG002
        return

    def persist(self) -> None:
        return

    # -- read ---------------------------------------------------------------

    def contains(self, surrogate: int) -> bool:
        stmt = select(graph_nodes.c.surrogate).where(graph_nodes.c.surrogate == surrogate)
        with self._engine.connect() as conn:
            return conn.execute(stmt).first() is not None

    def search(
        self,
        *,
        query_vector: Sequence[float],
        top_k: int,
        allowlist: Sequence[int] | None = None,
    ) -> list[tuple[int, float]]:
        """Exact cosine over ``graph_nodes``, restricted to the surrogate allowlist.

        ``allowlist=None`` → the whole index (the store always passes the user's
        set, so isolation never relies on None — design call #3); empty → ``[]``.
        Returns ``(surrogate, similarity)`` with ``similarity = 1 - cosine_distance``.
        """
        if allowlist is not None and len(allowlist) == 0:
            return []
        distance = graph_nodes.c.embedding.cosine_distance(list(query_vector)).label("distance")
        stmt = select(graph_nodes.c.surrogate, distance)
        if allowlist is not None:
            stmt = stmt.where(graph_nodes.c.surrogate.in_(list(allowlist)))
        stmt = stmt.order_by(distance).limit(top_k)
        with self._engine.connect() as conn:
            rows = conn.execute(stmt).all()
        return [(int(r[0]), 1.0 - float(r[1])) for r in rows]

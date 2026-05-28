"""The ``Backend`` transport protocol — the seam every storage backend fills.

The four typed stores (:mod:`persona.stores.base` ``TypedStore`` subclasses)
own policy, versioning, audit emission, and history/rollback — all
backend-agnostic. Underneath sits a *transport*: a narrow object that just
stores and retrieves chunks. :class:`persona.stores.chroma.ChromaBackend` is
the v0.1 local transport; :class:`persona.stores.postgres.PostgresBackend`
(spec 07) is the production transport. Both satisfy this protocol; the typed
stores compose either interchangeably (Liskov).

The surface is exactly ``ChromaBackend``'s — this protocol is reverse-engineered
from what that class already does, so adding a second backend is purely
additive. The method names are storage-neutral on purpose: ``delete_persona``
rather than Chroma's ``delete_collection`` (Postgres has rows, not collections).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from persona.schema.chunks import PersonaChunk

__all__ = ["Backend"]


@runtime_checkable
class Backend(Protocol):
    """The transport contract a :class:`TypedStore` composes.

    All methods are keyword-only past ``persona_id``/``store_kind`` to mirror
    the concrete backends and keep call sites self-documenting. The transport
    is dumb: it does no policy, versioning, or audit — those live in the typed
    store above it.
    """

    def upsert(
        self,
        *,
        persona_id: str,
        store_kind: str,
        chunks: list[PersonaChunk],
    ) -> None:
        """Insert or replace ``chunks`` for ``(persona_id, store_kind)``.

        Empty ``chunks`` is a no-op. The transport embeds each chunk's text
        via its injected embedder and stores the vector alongside the chunk.
        """
        ...

    def query(
        self,
        *,
        persona_id: str,
        store_kind: str,
        text: str,
        top_k: int,
        where: dict[str, Any] | None = None,  # noqa: ANN401 — backend-specific filter shape
    ) -> list[PersonaChunk]:
        """Return up to ``top_k`` chunks nearest to ``text`` by cosine distance.

        Each returned chunk has ``distance`` populated (cosine distance, where
        ``similarity = 1 - distance`` for L2-normalised embeddings). ``where``
        is a backend-specific metadata filter; ``None`` means no filter.
        """
        ...

    def get_all(
        self,
        *,
        persona_id: str,
        store_kind: str,
    ) -> list[PersonaChunk]:
        """Return every chunk for ``(persona_id, store_kind)`` (all versions)."""
        ...

    def delete_persona(self, persona_id: str, store_kind: str) -> None:
        """Remove every chunk for ``(persona_id, store_kind)``. Idempotent.

        Storage-neutral name for the per-persona-per-kind wipe. Chroma drops a
        collection; Postgres deletes rows. The caller does not know or care.
        """
        ...

    def delete_documents(
        self,
        *,
        persona_id: str,
        store_kind: str,
        ids: list[str],
    ) -> None:
        """Remove the listed chunk ids (not logical ids). Idempotent."""
        ...

"""The model-selection seam — cheap per-turn re-wrap (Spec 23 T10; D-23-X-seam-shape).

:func:`reorder_primary` is the load-bearing seam: given a tier's cached
:class:`~persona.backends.multi_model.MultiModelChatBackend` and a chosen model
id, it returns a FRESH wrapper over the SAME already-constructed sub-backends with
the chosen one first and the rest preserved in fallback order (Spec 20 D-20-9
chain intact). It NEVER mutates the cached wrapper (concurrency-safe — one wrapper
serves many conversations) and NEVER reconstructs a client (the
``MultiModelChatBackend.__init__`` is allocation-only — confirmed, so the re-wrap
is microseconds, well inside the Spec 18 D-18-4 ~30ms bound).

Short-circuits (D-23-X-seam-shape refinement 1): a non-wrapper backend, an
unknown chosen id, or chosen-already-primary all return the input unchanged with
zero allocation.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from persona.backends.multi_model import MultiModelChatBackend

if TYPE_CHECKING:
    from persona.backends.protocol import ChatBackend

__all__ = ["canonical_model_id", "reorder_primary"]


def canonical_model_id(provider: str, model: str) -> str:
    """Return the canonical provider-prefixed id for ``(provider, model)``.

    A model name that already carries a provider prefix (e.g. the OpenRouter
    slug ``"anthropic/claude-3.5-sonnet"``) is returned verbatim; a bare model
    name is prefixed with its provider (``"anthropic"``, ``"claude-sonnet-4-6"``
    → ``"anthropic/claude-sonnet-4-6"``). This is the id the metadata resolvers
    are keyed on.
    """
    return model if "/" in model else f"{provider}/{model}"


def reorder_primary(backend: ChatBackend, chosen_model_id: str) -> ChatBackend:
    """Return a backend whose PRIMARY is ``chosen_model_id`` (D-23-X-seam-shape).

    Args:
        backend: The tier's backend from
            :meth:`~persona_runtime.tier.TierRegistry.get` — usually a
            :class:`MultiModelChatBackend`.
        chosen_model_id: The canonical id the IntelligentRouter picked.

    Returns:
        ``backend`` unchanged when it is not a multi-model wrapper, the chosen id
        is not among its sub-backends, or the chosen model is already the primary
        (slot 0). Otherwise a fresh :class:`MultiModelChatBackend` over the same
        sub-backend instances, chosen first, the rest in their original relative
        order (fallback chain preserved).
    """
    if not isinstance(backend, MultiModelChatBackend):
        return backend
    subs = backend.backends
    chosen_index: int | None = None
    for i, sub in enumerate(subs):
        if canonical_model_id(sub.provider_name, sub.model_name) == chosen_model_id:
            chosen_index = i
            break
    if chosen_index is None or chosen_index == 0:
        # Unknown id, or already primary → no re-wrap, no allocation.
        return backend
    reordered = [subs[chosen_index], *subs[:chosen_index], *subs[chosen_index + 1 :]]
    return MultiModelChatBackend(reordered, tier_name=backend.tier_name)

"""The credits seam (Spec 33, §2.2 / D-33-X-creditspolicy-di).

``CreditsPolicy`` is the interface every metered op calls — injected via
``app.state`` (mirroring how ``rls_engine`` is threaded), so call sites never
import the concrete service and there are no scattered ``if edition`` checks
(acceptance criterion 3).

- :class:`MeteredCreditsPolicy` delegates to the existing ``persona.credits``
  surface — cloud, behavior unchanged.
- :class:`UnlimitedCreditsPolicy` — community: every check passes, deduct/refund
  are no-ops, balance reads return a large constant. Never touches the DB
  (community has no credits ledger to consult).

The method surface mirrors ``persona.credits`` exactly (keyword-only,
``rls_engine`` + ``user_id`` …) so the swap is a drop-in at every call site.
"""

# The community no-op methods intentionally ignore their interface arguments
# (they must keep the exact parameter NAMES so keyword call sites are
# drop-in-compatible, so they cannot be renamed to ``_``).
# ruff: noqa: ARG002

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from persona.credits import (
    deduct as _deduct,
)
from persona.credits import (
    get_balance as _get_balance,
)
from persona.credits import (
    list_turn_usage as _list_turn_usage,
)
from persona.credits import (
    list_usage as _list_usage,
)
from persona.credits import (
    refund as _refund,
)
from persona.credits import (
    require_credits as _require_credits,
)

if TYPE_CHECKING:
    from sqlalchemy import Engine

__all__ = [
    "CreditsPolicy",
    "MeteredCreditsPolicy",
    "UnlimitedCreditsPolicy",
]

# The notional balance the community policy reports — large enough that any UI
# low-balance threshold reads "plenty", small enough to be obviously sentinel.
_UNLIMITED_BALANCE = 1_000_000_000


@runtime_checkable
class CreditsPolicy(Protocol):
    """Pre-flight gate + ledger moves for metered operations."""

    def require_credits(self, *, rls_engine: Engine, user_id: str) -> int:
        """Pre-flight check; raise ``CreditsExhaustedError`` (→ 402) if empty."""
        ...

    def deduct(self, *, rls_engine: Engine, user_id: str, amount: int, reason: str) -> int:
        """Deduct ``amount`` + record a ledger row. Returns the new balance."""
        ...

    def refund(self, *, rls_engine: Engine, user_id: str, amount: int, reason: str) -> int:
        """Reverse-deduct via a ledger entry. Returns the new balance."""
        ...

    def get_balance(self, *, rls_engine: Engine, user_id: str) -> int:
        """The current balance."""
        ...

    def list_usage(
        self, *, rls_engine: Engine, user_id: str, limit: int, offset: int
    ) -> list[dict[str, object]]:
        """The credit-transaction log (paginated)."""
        ...

    def list_turn_usage(
        self, *, rls_engine: Engine, limit: int, offset: int
    ) -> list[dict[str, object]]:
        """Per-turn token usage (paginated)."""
        ...


class MeteredCreditsPolicy:
    """Cloud: the existing metered ledger (delegates to ``persona.credits``)."""

    def require_credits(self, *, rls_engine: Engine, user_id: str) -> int:
        return _require_credits(rls_engine=rls_engine, user_id=user_id)

    def deduct(self, *, rls_engine: Engine, user_id: str, amount: int, reason: str) -> int:
        return _deduct(rls_engine=rls_engine, user_id=user_id, amount=amount, reason=reason)

    def refund(self, *, rls_engine: Engine, user_id: str, amount: int, reason: str) -> int:
        return _refund(rls_engine=rls_engine, user_id=user_id, amount=amount, reason=reason)

    def get_balance(self, *, rls_engine: Engine, user_id: str) -> int:
        return _get_balance(rls_engine=rls_engine, user_id=user_id)

    def list_usage(
        self, *, rls_engine: Engine, user_id: str, limit: int, offset: int
    ) -> list[dict[str, object]]:
        return _list_usage(rls_engine=rls_engine, user_id=user_id, limit=limit, offset=offset)

    def list_turn_usage(
        self, *, rls_engine: Engine, limit: int, offset: int
    ) -> list[dict[str, object]]:
        return _list_turn_usage(rls_engine=rls_engine, limit=limit, offset=offset)


class UnlimitedCreditsPolicy:
    """Community: unmetered — every check passes, moves are no-ops (D-33-X-creditspolicy-di)."""

    def require_credits(self, *, rls_engine: Engine, user_id: str) -> int:
        return _UNLIMITED_BALANCE

    def deduct(self, *, rls_engine: Engine, user_id: str, amount: int, reason: str) -> int:
        return _UNLIMITED_BALANCE

    def refund(self, *, rls_engine: Engine, user_id: str, amount: int, reason: str) -> int:
        return _UNLIMITED_BALANCE

    def get_balance(self, *, rls_engine: Engine, user_id: str) -> int:
        return _UNLIMITED_BALANCE

    def list_usage(
        self, *, rls_engine: Engine, user_id: str, limit: int, offset: int
    ) -> list[dict[str, object]]:
        return []

    def list_turn_usage(
        self, *, rls_engine: Engine, limit: int, offset: int
    ) -> list[dict[str, object]]:
        return []

"""JIT user provisioning (spec-09 integration).

A third-party provider (Clerk) issues JWTs; spec 08 deferred webhook
user-mirroring, so a freshly-authenticated user has no ``users`` row — yet
personas/conversations/runs/credits all FK ``users.id``. The auth dependency
calls :func:`ensure_user` on each request to idempotently create the row, run on
the **superuser** engine (a *system* action, not the user acting under RLS). The
production path is a provider webhook; this JIT upsert is the v0.1 equivalent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy import Engine

__all__ = ["ensure_user"]


def ensure_user(engine: Engine, *, user_id: str, email: str | None) -> None:
    """Idempotently insert the ``users`` row (no-op if it already exists).

    Uses a superuser engine (bypasses RLS — provisioning is a system action).
    ``email`` is NOT NULL + unique in the schema; falls back to a noreply
    address when the token carries none. Parameterised (no interpolation).
    """
    resolved_email = email or f"{user_id}@users.noreply"
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO users (id, email) VALUES (:id, :email) ON CONFLICT (id) DO NOTHING"),
            {"id": user_id, "email": resolved_email},
        )

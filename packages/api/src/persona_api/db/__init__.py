"""Database layer for the hosted service (spec 07).

``models`` holds the canonical SQLAlchemy Core schema; ``engine`` (T06) holds
the engine/session factory and the RLS ``set_config`` plumbing; ``rls`` (T06)
holds the policy SQL. The FastAPI routes/services (spec 08) compose these.
"""

from __future__ import annotations

from persona_api.db.engine import create_db_engine, rls_connection, set_current_user
from persona_api.db.models import EMBEDDING_DIM, STORE_KINDS, metadata
from persona_api.db.rls import RLS_TABLES, downgrade_rls_sql, upgrade_rls_sql

__all__ = [
    "EMBEDDING_DIM",
    "RLS_TABLES",
    "STORE_KINDS",
    "create_db_engine",
    "downgrade_rls_sql",
    "metadata",
    "rls_connection",
    "set_current_user",
    "upgrade_rls_sql",
]

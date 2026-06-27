"""Core-owned minimal view of the ``calls`` table (Spec V9, V9-D-5).

A voice call's durable lifecycle envelope lives in the api-owned ``calls`` table
(``persona_api.db.models.calls``), but the **writer** is the API-free voice
runtime (``voice → runtime → core``, never persona-api). So — exactly like
``memory_chunks`` (``persona.stores.postgres._memory_chunks``) — this module
defines core's OWN minimal :class:`~sqlalchemy.Table` view of ``calls``: the
voice ``CallRecorder`` writes through it on the session RLS engine, with no
persona-api import. Column names/types MIRROR ``persona_api.db.models.calls``;
api owns the DDL (migration 020) and a contract test guards the drift.

The view is intentionally minimal — only the columns the recorder writes/reads.
``created_at`` carries the table's ``server_default`` on the api side, so the
recorder never sets it.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, MetaData, Table, Text, func

__all__ = ["calls"]

# A private MetaData so importing this module never collides with the api schema
# registry (mirrors ``persona.stores.postgres._md``).
_md = MetaData()

#: Core's minimal write/read view of the api ``calls`` table. Column names/types
#: mirror ``persona_api.db.models.calls``; the contract test guards drift.
calls = Table(
    "calls",
    _md,
    Column("call_id", Text, primary_key=True),
    Column("conversation_id", Text, nullable=False),
    Column("persona_id", Text, nullable=False),
    Column("owner_id", Text, nullable=False),
    Column("started_at", DateTime(timezone=True), nullable=False),
    Column("ended_at", DateTime(timezone=True)),
    Column("duration_s", Integer),
    Column("end_reason", Text),
    # The DB fills this server-side (mirrors the api table's ``func.now()``); the
    # recorder never sets it. Declared here so the view is faithful and a
    # ``create_all`` of this view (unit tests) carries the same default.
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

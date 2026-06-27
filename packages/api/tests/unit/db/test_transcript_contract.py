"""Contract: core's ``messages`` view never drifts from the api ``messages`` table.

Spec V9 (V9-D-1/D-2), the ``memory_chunks`` / ``calls`` precedent: the API-free
voice runtime persists the per-call transcript through core's OWN minimal
:class:`~sqlalchemy.Table` view (``persona.transcript.messages``) because it
cannot import the api schema. This asserts the two Table defs carry the SAME
columns, so the voice transcript writer can never silently diverge from the
migrated DDL (e.g. miss a NOT-NULL column → a broken write at runtime). Pure
in-memory comparison — no DB.
"""

from __future__ import annotations

from persona.transcript import messages as core_view
from persona_api.db.models import messages as api_table


def test_core_messages_view_matches_api_messages_schema() -> None:
    core_cols = {c.name for c in core_view.c}
    api_cols = {c.name for c in api_table.c}
    assert core_cols == api_cols, (
        f"core messages view diverged from api schema: "
        f"core-only={core_cols - api_cols}, api-only={api_cols - core_cols}"
    )

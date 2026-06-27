"""Contract: core's ``_calls`` view never drifts from the api ``calls`` table.

Spec V9 (V9-D-5), the ``memory_chunks`` precedent (``test_migration``'s
``test_core_transport_view_matches_migrated_schema``): the API-free voice runtime
writes the call-record through core's OWN minimal :class:`~sqlalchemy.Table` view
(``persona.calls.calls``) because it cannot import the api schema. This asserts
the two Table defs carry the SAME columns, so the voice writer can never silently
diverge from the migrated DDL. Pure in-memory comparison — no DB.
"""

from __future__ import annotations

from persona.calls import calls as core_view
from persona_api.db.models import calls as api_table


def test_core_calls_view_matches_api_calls_schema() -> None:
    core_cols = {c.name for c in core_view.c}
    api_cols = {c.name for c in api_table.c}
    assert core_cols == api_cols, (
        f"core calls view diverged from api schema: "
        f"core-only={core_cols - api_cols}, api-only={api_cols - core_cols}"
    )

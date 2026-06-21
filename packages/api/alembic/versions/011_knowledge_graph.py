"""Knowledge-graph store: ``graph_nodes`` / ``graph_edges`` / ``graph_entities`` (Spec K0, T4).

Adds the three user-scoped graph tables plus their row-level-security policies,
mirroring migration ``009`` (tables from the canonical ``MetaData`` via
``create(checkfirst=True)``; RLS owned ENTIRELY here with ``DROP POLICY IF EXISTS``
idempotence — so ``001``'s downgrade never ALTERs a later table).

RLS is the **direct ``owner_id``** policy (the graph is per *user*, not the
persona FK-chain), ENABLE + FORCE, fail-closed: ``current_setting(...,true)``
yields NULL when the GUC is unset → matches no row.

> **Migration ordering (placeholder — do NOT treat as final).** ``revision`` and
> ``down_revision`` are placeholders. Both this spec (K0) and A0 (durable
> execution) develop in parallel worktrees on ``down_revision = "010"``; the
> orchestrator **linearizes them in merge order at merge-back** (re-points one's
> ``down_revision`` at the other's ``revision``). Do NOT hardcode a successor
> (e.g. ``012``).

Revision ID: 011_knowledge_graph
Revises: 010_add_message_tier
"""

from __future__ import annotations

from alembic import op
from persona_api.db.models import graph_edges, graph_entities, graph_node_entities, graph_nodes

revision = "011_knowledge_graph"
down_revision = "010_add_message_tier"
branch_labels = None
depends_on = None

_CUR = "current_setting('app.current_user_id', true)"

# (table, USING/WITH CHECK predicate) — direct owner_id (user-scope) variant.
# All three tables key on owner_id, so the predicate is uniform.
_RLS: tuple[tuple[str, str], ...] = (
    ("graph_nodes", f"owner_id = {_CUR}"),
    ("graph_edges", f"owner_id = {_CUR}"),
    ("graph_entities", f"owner_id = {_CUR}"),
    ("graph_node_entities", f"owner_id = {_CUR}"),
)


def upgrade() -> None:
    bind = op.get_bind()
    # pgvector for the embedding columns (no-op if 001 already created it).
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    # FK order: nodes first (edges composite-FK to them), then edges, then entities,
    # then the node↔entity join (composite-FKs both nodes and entities).
    graph_nodes.create(bind, checkfirst=True)
    graph_edges.create(bind, checkfirst=True)
    graph_entities.create(bind, checkfirst=True)
    graph_node_entities.create(bind, checkfirst=True)
    for table, predicate in _RLS:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        # DROP IF EXISTS keeps this idempotent + avoids clashing with a policy a
        # fresh-install 001 create_all path might have made (tables are in metadata).
        op.execute(f"DROP POLICY IF EXISTS user_isolation ON {table}")
        op.execute(
            f"CREATE POLICY user_isolation ON {table} USING ({predicate}) WITH CHECK ({predicate})"
        )


def downgrade() -> None:
    bind = op.get_bind()
    for table, _ in _RLS:
        op.execute(f"DROP POLICY IF EXISTS user_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    # Reverse FK order: the join (references nodes+entities) first, then edges,
    # then nodes, then entities.
    graph_node_entities.drop(bind, checkfirst=True)
    graph_edges.drop(bind, checkfirst=True)
    graph_nodes.drop(bind, checkfirst=True)
    graph_entities.drop(bind, checkfirst=True)

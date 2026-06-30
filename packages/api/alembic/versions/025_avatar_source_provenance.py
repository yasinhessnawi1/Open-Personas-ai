"""Add ``avatar_source`` synthetic-media provenance to ``personas`` (Spec R3, R3-D-2).

EU AI Act Article 50 (binding 2026-08-02) requires that AI-generated images be
recorded generated-vs-uploaded and disclosed to the recipient. This migration
adds the durable provenance signal for the **avatar** surface — the one image
surface whose record-of-truth is a DB row (the chat-image surface already
carries the signal at the workspace-sidecar layer, R3-D-4).

One nullable column:

- ``avatar_source TEXT NULL`` — ``'generated'`` (system image-gen path:
  the inline create-hook or the async avatar job), ``'uploaded'`` (a user
  supplied the bytes via the upload-to-change PATCH), or ``NULL`` = **unknown**.
  TEXT (not an SQL ENUM/CHECK) so the community **SQLite** edition is
  byte-identical to Postgres — the value vocabulary is enforced at the app layer
  (R3-D-2). The Art. 50 "AI-generated" disclosure is *derived* from this stored
  signal (``avatar_source == 'generated'``), never guessed; the write paths set
  it in the SAME ``UPDATE`` as ``avatar_url`` so it is unforgeable (R3-D-3).

**Backfill = NULL = unknown (R3-D-5).** Every persona that predates this column
reads ``NULL`` (the ``ADD COLUMN`` default) — no data migration. This is the
honest floor: the audit log records *generation* events but not *uploads*, so a
backfill could mark only the generated side and would silently mislabel every
pre-existing upload. A uniform, explicit "unknown" is truthful; Art. 50 is
forward-looking (new content is marked correctly).

Additive + nullable, so every existing persona is byte-for-byte unaffected and
loads as ``NULL``. RLS is row-level on ``owner_id``; a new nullable column
inherits the table policy — no RLS change. ``avatar_source`` is an API-row
presentation field like ``avatar_url`` (migration 003), NOT part of the persona
YAML schema, so ``schema_version`` does not move.

Split-home (cf. migrations 008 / 020 / 023 / 024): the same column is declared on
the canonical ``persona_api.db.models.personas`` table, so on a fresh DB —
including the community SQLite edition — ``001_initial``'s
``metadata.create_all`` already builds it and the guarded ``ADD COLUMN IF NOT
EXISTS`` below is a harmless no-op; on a previously-deployed Postgres it actually
adds the column. Both agree.

Revision ID: 025_avatar_source_provenance
Revises: 024_credits_balance_floor
Create Date: 2026-06-30
"""

from __future__ import annotations

from alembic import op

# PLACEHOLDER down_revision (R-19-1 chain numbering): chained off main's head at
# authoring time, ``024_credits_balance_floor`` (R2 — the verified single head when
# R3 branched). Other in-flight specs (R-/C-/N-/P-track) may land migrations before
# R3 merges, so this number + ``down_revision`` are RECOMPUTED at merge-back to
# preserve the single-head chain — do NOT rely on ``025`` / ``024`` surviving verbatim.
revision = "025_avatar_source_provenance"
down_revision = "024_credits_balance_floor"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ``ADD COLUMN IF NOT EXISTS`` per the 008 / 020 precedent: ``001_initial``
    # builds the schema via ``MetaData.create_all`` from the *live* models (which
    # now declare ``avatar_source``), so on a fresh DB the column already exists
    # when ``025`` runs (harmless no-op); on a DB that ran ``001`` before R3 the
    # column is genuinely added. NULL default = the R3-D-5 unknown backfill — no
    # data migration.
    op.execute("ALTER TABLE personas ADD COLUMN IF NOT EXISTS avatar_source TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE personas DROP COLUMN IF EXISTS avatar_source")

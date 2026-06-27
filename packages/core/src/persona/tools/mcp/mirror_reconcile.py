"""Catalog-mirror reconcile/diff — the auto-sync's idempotent write (Spec N2 T1).

N2 keeps N1's mirror fresh automatically. N1's :func:`~persona.tools.mcp.mirror_sync.sync_mirror`
does a full atomic *replace* and returns only a count — it cannot report what changed. This
module is the thin **diff** layer over N1's shared pull seam
(:func:`~persona.tools.mcp.mirror_sync.build_entries_from_source` +
:func:`~persona.tools.mcp.mirror_sync.write_mirror_atomic`):

1. load the EXISTING snapshot (or treat an absent/unreadable one as empty);
2. build the NEW entries from the registry (reusing N1's clone/parse — no reinvention);
3. compute **added / updated / removed** over a name-keyed diff (criterion 5 observability);
4. write the new snapshot **atomically** (N1's temp+rename — a failure leaves the last good
   mirror intact, D-N1-4).

Idempotency (criterion 2): ``MCPServerCatalogEntry`` is a frozen Pydantic model, so equality is
value-equality — re-running against an unchanged registry yields an all-zero diff AND a
byte-identical file (N1 writes ``sort_keys=True``). A **removed** server appears in
:attr:`MirrorSyncResult.removed` and is dropped from the snapshot, so it is never offered as
newly-enableable (N2-D-4 surface a) and the loss is observable rather than silent (surface b).

**OFFLINE-ONLY** — like ``mirror_sync``, this is the maintainer/auto-refresh path (git + network +
YAML live here), never reached from the request path (the request-time loader is
:mod:`persona.tools.mcp.mirror`).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, ValidationError

from persona.logging import get_logger
from persona.tools.mcp.catalog import MCPServerCatalogEntry
from persona.tools.mcp.mirror_sync import build_entries_from_source, write_mirror_atomic

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

__all__ = ["MirrorSyncResult", "diff_entries", "reconcile_mirror"]

_log = get_logger("tools.mcp.mirror_reconcile")


class MirrorSyncResult(BaseModel):
    """The outcome of one reconcile — what changed, for observability (N2-D-6).

    Attributes:
        added: Names present in the new snapshot but not the old, sorted.
        updated: Names present in both whose entry value changed (any field — incl.
            ``source_commit``/``description``/``image``/``secrets``), sorted.
        removed: Names present in the old snapshot but not the new, sorted (surfaced,
            never silent — N2-D-4 surface b).
        total: The total server count in the new snapshot.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    added: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]
    total: int


def diff_entries(
    old: Mapping[str, MCPServerCatalogEntry],
    new: Sequence[MCPServerCatalogEntry],
) -> MirrorSyncResult:
    """Classify the change between an old snapshot and freshly-built entries.

    A pure, name-keyed diff over frozen-model value-equality: ``added`` = new names not in
    old; ``removed`` = old names not in new; ``updated`` = names in both whose entry differs.
    All three lists are sorted for a deterministic, log-stable result.

    Args:
        old: The previous snapshot, name → entry (empty when there was none).
        new: The freshly-built entries.

    Returns:
        The :class:`MirrorSyncResult` counts.
    """
    new_by_name = {e.name: e for e in new}
    old_names = set(old)
    new_names = set(new_by_name)
    added = sorted(new_names - old_names)
    removed = sorted(old_names - new_names)
    updated = sorted(name for name in old_names & new_names if old[name] != new_by_name[name])
    return MirrorSyncResult(
        added=tuple(added),
        updated=tuple(updated),
        removed=tuple(removed),
        total=len(new_by_name),
    )


def _load_existing_entries(path: Path) -> dict[str, MCPServerCatalogEntry]:
    """Read the existing snapshot's entries, or ``{}`` if absent/unreadable/invalid.

    Deliberately NOT :func:`~persona.tools.mcp.mirror.load_mirror_catalog` — that fails soft to
    the *builtin* catalog, which would corrupt the diff (it would diff against the builtins, not
    the prior mirror). For a reconcile we need the literal prior file; an unreadable one is
    honestly "no prior state" → everything counts as added, and the file is rewritten clean.
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        entries: dict[str, MCPServerCatalogEntry] = {}
        for item in raw["servers"]:
            entry = MCPServerCatalogEntry.model_validate(item)
            entries[entry.name] = entry
    except (OSError, ValueError, KeyError, TypeError, ValidationError) as exc:
        _log.warning(
            "existing mirror snapshot unreadable; treating as empty for reconcile",
            path=str(path),
            error=type(exc).__name__,
        )
        return {}
    return entries


def reconcile_mirror(
    *,
    repo: str | None = None,
    mirror_path: Path,
    registry_root: Path | None = None,
) -> MirrorSyncResult:
    """Reconcile the mirror snapshot at ``mirror_path`` against the registry (OFFLINE-ONLY).

    Loads the existing snapshot, builds the new entries from the registry (a local checkout or
    a fresh clone via N1's shared pull seam), diffs them, and writes the new snapshot atomically.
    A clone/parse failure raises BEFORE the write, leaving the last good mirror intact (D-N1-4).

    Args:
        repo: The registry git URL (defaults to N1's ``REGISTRY_REPO``; ignored when
            ``registry_root`` is given).
        mirror_path: The snapshot file to reconcile (read for the old state, written with the new).
        registry_root: An existing local checkout to read instead of cloning (tests / local runs).

    Returns:
        The :class:`MirrorSyncResult` describing what changed.

    Raises:
        FileNotFoundError: the checkout has no ``servers/`` directory.
        subprocess.CalledProcessError: the git clone failed.
    """
    from persona.tools.mcp.mirror_sync import REGISTRY_REPO

    old = _load_existing_entries(mirror_path)
    new = build_entries_from_source(repo=repo or REGISTRY_REPO, registry_root=registry_root)
    result = diff_entries(old, new)
    write_mirror_atomic(new, mirror_path)
    _log.info(
        "mcp mirror reconciled",
        path=str(mirror_path),
        added=len(result.added),
        updated=len(result.updated),
        removed=len(result.removed),
        total=result.total,
    )
    return result

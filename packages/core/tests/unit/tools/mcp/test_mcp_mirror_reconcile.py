"""Unit tests for the catalog-mirror reconcile/diff (Spec N2 T1, N2-D-4 / N2-D-6).

The reconcile is the thin diff layer over N1's offline pull (``build_mirror_entries``
/ ``write_mirror_atomic``): it loads the EXISTING snapshot, builds the NEW entries,
computes added/updated/removed counts (criterion 5), and writes atomically. Re-running
against an unchanged source is a provable no-op — all-zero diff + a byte-identical file
(criterion 2 idempotency). A removed server appears in ``removed`` (N2-D-4 surface b),
never silently.
"""

from __future__ import annotations

import textwrap
from typing import TYPE_CHECKING

from persona.tools.mcp.mirror import load_mirror_catalog
from persona.tools.mcp.mirror_reconcile import (
    MirrorSyncResult,
    diff_entries,
    reconcile_mirror,
)
from persona.tools.mcp.mirror_sync import build_mirror_entries, write_mirror_atomic

if TYPE_CHECKING:
    from pathlib import Path


def _server_yaml(*, title: str, description: str, commit: str) -> str:
    return textwrap.dedent(
        f"""
        name: srv
        image: ghcr.io/example/srv
        type: server
        about:
          title: {title}
          description: {description}
        source:
          project: https://github.com/example/srv
          commit: {commit}
        """
    )


def _write_server(registry_root: Path, name: str, body: str) -> None:
    d = registry_root / "servers" / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "server.yaml").write_text(body, encoding="utf-8")


# --------------------------------------------------------------------------- #
# diff_entries — the pure name-keyed diff over frozen-model equality          #
# --------------------------------------------------------------------------- #


def test_diff_classifies_added_updated_removed(tmp_path: Path) -> None:
    old_registry = tmp_path / "old"
    _write_server(
        old_registry, "keep", _server_yaml(title="Keep", description="k", commit="a" * 40)
    )
    _write_server(
        old_registry, "gone", _server_yaml(title="Gone", description="g", commit="b" * 40)
    )
    old = {e.name: e for e in build_mirror_entries(old_registry)}

    new_registry = tmp_path / "new"
    # keep: unchanged; gone: removed; changed: same name, new commit; fresh: added
    _write_server(
        new_registry, "keep", _server_yaml(title="Keep", description="k", commit="a" * 40)
    )
    _write_server(
        new_registry, "changed", _server_yaml(title="Keep", description="k", commit="a" * 40)
    )
    _write_server(
        new_registry, "fresh", _server_yaml(title="Fresh", description="f", commit="c" * 40)
    )
    # Rename keep→changed is just add+remove; make 'changed' a true update of 'keep':
    new = {e.name: e for e in build_mirror_entries(new_registry)}
    # Recompose: 'keep' present in both but with a CHANGED commit to exercise "updated".
    changed_keep = old["keep"].model_copy(update={"source_commit": "d" * 40})
    new["keep"] = changed_keep
    del new["changed"]

    result = diff_entries(old, list(new.values()))
    assert result.added == ("fresh",)
    assert result.updated == ("keep",)  # same name, different field value
    assert result.removed == ("gone",)
    assert result.total == len(new)


def test_diff_unchanged_is_all_zero(tmp_path: Path) -> None:
    reg = tmp_path / "reg"
    _write_server(reg, "srv", _server_yaml(title="S", description="d", commit="a" * 40))
    entries = build_mirror_entries(reg)
    old = {e.name: e for e in entries}
    result = diff_entries(old, entries)
    assert result == MirrorSyncResult(added=(), updated=(), removed=(), total=1)


# --------------------------------------------------------------------------- #
# reconcile_mirror — load existing → build new → diff → atomic write          #
# --------------------------------------------------------------------------- #


def test_reconcile_against_absent_mirror_counts_all_added(tmp_path: Path) -> None:
    reg = tmp_path / "reg"
    _write_server(reg, "srv", _server_yaml(title="S", description="d", commit="a" * 40))
    mirror = tmp_path / "mirror.json"
    result = reconcile_mirror(mirror_path=mirror, registry_root=reg)
    assert result.added == ("srv",)
    assert result.updated == ()
    assert result.removed == ()
    assert load_mirror_catalog(mirror).servers.keys() == {"srv"}


def test_reconcile_is_idempotent_byte_identical(tmp_path: Path) -> None:
    reg = tmp_path / "reg"
    _write_server(reg, "srv", _server_yaml(title="S", description="d", commit="a" * 40))
    mirror = tmp_path / "mirror.json"
    reconcile_mirror(mirror_path=mirror, registry_root=reg)
    first = mirror.read_bytes()

    second_result = reconcile_mirror(mirror_path=mirror, registry_root=reg)
    assert second_result == MirrorSyncResult(added=(), updated=(), removed=(), total=1)
    assert mirror.read_bytes() == first  # byte-identical — no churn (criterion 2)


def test_reconcile_reports_removed_server(tmp_path: Path) -> None:
    # First sync has two servers; second drops one → it must appear in `removed`.
    reg1 = tmp_path / "reg1"
    _write_server(reg1, "a", _server_yaml(title="A", description="a", commit="a" * 40))
    _write_server(reg1, "b", _server_yaml(title="B", description="b", commit="b" * 40))
    mirror = tmp_path / "mirror.json"
    reconcile_mirror(mirror_path=mirror, registry_root=reg1)

    reg2 = tmp_path / "reg2"
    _write_server(reg2, "a", _server_yaml(title="A", description="a", commit="a" * 40))
    result = reconcile_mirror(mirror_path=mirror, registry_root=reg2)
    assert result.removed == ("b",)
    # The removed server is gone from the availability snapshot (N2-D-4 surface a).
    assert load_mirror_catalog(mirror).servers.keys() == {"a"}


def test_reconcile_corrupt_existing_mirror_treats_all_as_added(tmp_path: Path) -> None:
    # An unreadable existing snapshot must not crash the reconcile; we couldn't read
    # the old state, so everything is honestly "added" and the file is rewritten.
    mirror = tmp_path / "mirror.json"
    mirror.write_text("{ not valid json", encoding="utf-8")
    reg = tmp_path / "reg"
    _write_server(reg, "srv", _server_yaml(title="S", description="d", commit="a" * 40))
    result = reconcile_mirror(mirror_path=mirror, registry_root=reg)
    assert result.added == ("srv",)
    assert load_mirror_catalog(mirror).servers.keys() == {"srv"}


def test_reconcile_writes_only_the_mirror_not_other_state(tmp_path: Path) -> None:
    # N2-D-5 (criterion 4) STRUCTURAL proof: the sync's ONLY write target is the mirror
    # snapshot. A sentinel standing in for ANY other persisted state (e.g. a persona's
    # enablement allow-list) must be byte-untouched — the sync changes AVAILABILITY, and
    # has no handle to reach ENABLEMENT. (reconcile_mirror takes only a mirror_path +
    # registry; there is no persona/allow-list collaborator in its dependency graph.)
    enablement = tmp_path / "persona_enablement.json"
    enablement.write_text('{"persona_x": {"tools": ["file_read"]}}', encoding="utf-8")
    enablement_before = enablement.read_bytes()

    reg = tmp_path / "reg"
    _write_server(reg, "newserver", _server_yaml(title="New", description="n", commit="e" * 40))
    mirror = tmp_path / "mirror.json"
    result = reconcile_mirror(mirror_path=mirror, registry_root=reg)

    assert result.added == ("newserver",)  # availability rose
    assert mirror.exists()  # the mirror was written
    assert enablement.read_bytes() == enablement_before  # enablement state byte-untouched


def test_reconcile_failure_preserves_last_good_mirror(tmp_path: Path) -> None:
    reg = tmp_path / "reg"
    _write_server(reg, "srv", _server_yaml(title="S", description="d", commit="a" * 40))
    mirror = tmp_path / "mirror.json"
    write_mirror_atomic(build_mirror_entries(reg), mirror)
    before = mirror.read_bytes()

    import pytest

    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FileNotFoundError):
        reconcile_mirror(mirror_path=mirror, registry_root=empty)
    assert mirror.read_bytes() == before  # last good snapshot intact

"""Spec F5 T05 — producer-touch test for imagegen service sidecar writes.

Validates that ``imagegen.service._persist_bytes`` writes a
``WorkspaceArtifactMetadata`` sidecar with source="generated",
type="image", producing_spec="15" per D-F5-X-artifact-metadata-convention.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from persona_api.imagegen.service import _persist_bytes
from persona_api.services.artifact_metadata import (
    SIDECAR_SUFFIX,
    read_artifact_sidecar,
)


def _make_png() -> bytes:
    try:
        from PIL import Image  # type: ignore[import-not-found]
    except ImportError:
        pytest.skip("Pillow not installed; required for image bytes")
    img = Image.new("RGB", (16, 16), (0, 128, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture
def png_bytes() -> bytes:
    return _make_png()


def test_imagegen_persist_writes_f5_sidecar(tmp_path: Path, png_bytes: bytes) -> None:
    sandbox = tmp_path / "u1" / "astrid"
    sandbox.mkdir(parents=True)

    relative = _persist_bytes(
        sandbox_root=sandbox,
        image_bytes=png_bytes,
        media_type="image/png",
    )

    bytes_path = sandbox / relative
    assert bytes_path.is_file()

    sidecar = bytes_path.parent / f"{bytes_path.name}{SIDECAR_SUFFIX}"
    assert sidecar.is_file()

    meta = read_artifact_sidecar(bytes_path)
    assert meta is not None
    assert meta.source == "generated"
    assert meta.type == "image"
    assert meta.producing_spec == "15"
    assert meta.conversation_id is None
    assert meta.original_name is None


def test_imagegen_persist_with_conversation_id(tmp_path: Path, png_bytes: bytes) -> None:
    sandbox = tmp_path / "u1" / "astrid"
    sandbox.mkdir(parents=True)

    relative = _persist_bytes(
        sandbox_root=sandbox,
        image_bytes=png_bytes,
        media_type="image/png",
        conversation_id="conv-42",
    )

    bytes_path = sandbox / relative
    meta = read_artifact_sidecar(bytes_path)
    assert meta is not None
    assert meta.conversation_id == "conv-42"


def test_imagegen_sidecar_failure_does_not_abort_persist(
    tmp_path: Path,
    png_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sidecar write failure must not break the persist (bytes are primary)."""
    sandbox = tmp_path / "u1" / "astrid"
    sandbox.mkdir(parents=True)

    def _raise(*_args: object, **_kwargs: object) -> None:
        raise OSError("simulated")

    import persona_api.services.artifact_metadata as am

    monkeypatch.setattr(am, "write_artifact_sidecar", _raise)

    relative = _persist_bytes(
        sandbox_root=sandbox,
        image_bytes=png_bytes,
        media_type="image/png",
    )

    bytes_path = sandbox / relative
    assert bytes_path.is_file()
    sidecar = bytes_path.parent / f"{bytes_path.name}{SIDECAR_SUFFIX}"
    assert not sidecar.is_file()

"""Hosted-sandbox produced-file discovery parity (rich-output fix).

The hosted E2B path returned ``produced_files`` ALWAYS EMPTY — a produced PNG
never became a ``ToolResult`` artifact, so the chat UI rendered only stdout text,
never the image. This is the hosted analogue of
``LocalDockerSandbox._discover_produced_files``: after a ``code_execution`` run we
list the documented ``/workspace/out`` out-dir over the E2B SDK filesystem API
and surface each file as an ``ExecutionResult.produced_files`` entry with the
media type inferred from the extension — the SAME shape the local Docker path
emits and the frontend already consumes (``inline-image`` via
``media_type.startswith("image/")``).

The E2B client is faked to the VERIFIED real SDK shape (confirmed against a live
sandbox before writing this):

  * ``files.list(path, depth=...)`` → ``list[EntryInfo]``; each entry exposes
    ``name`` (basename), ``path`` (absolute, e.g. ``/workspace/out/chart.png``),
    ``type`` (a ``FileType`` enum whose ``.value`` is ``"file"`` / ``"dir"``),
    and ``size`` (int bytes). ``depth=1`` is non-recursive; ``depth>1`` recurses
    and returns nested files (e.g. ``/workspace/out/charts/sales.png``) plus the
    intermediate DIR entries.
  * ``files.read(path, format="bytes")`` → a ``bytearray`` (NOT ``bytes``).
  * ``files.list`` on a missing directory raises ``NotFoundException``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import pytest
from persona.sandbox.result import ResourceLimits
from persona_api.sandbox.hosted import _HOSTED_WORKSPACE_OUT, HostedSandbox


class _FileType(Enum):
    """Stand-in mirroring the SDK ``e2b.FileType`` enum (value ``"file"`` / ``"dir"``)."""

    FILE = "file"
    DIR = "dir"


@dataclass
class _EntryInfo:
    """Stand-in for the SDK ``EntryInfo`` dataclass (verified fields only)."""

    name: str
    type: _FileType
    path: str
    size: int


class _FakeFiles:
    """Stand-in for ``sandbox.files`` with the verified ``list`` / ``read`` shape."""

    def __init__(
        self, entries: list[_EntryInfo], *, read_payloads: dict[str, bytes] | None = None
    ) -> None:
        self._entries = entries
        self._read_payloads = read_payloads or {}
        self.list_calls: list[tuple[str, int | None]] = []
        self.read_paths: list[str] = []

    def list(  # noqa: A003 — mirrors SDK name
        self, path: str, *, depth: int | None = None
    ) -> list[_EntryInfo]:
        self.list_calls.append((path, depth))
        if not any(e.path.startswith(path) for e in self._entries):
            # Mirror the SDK: listing a missing dir raises (NotFoundException).
            raise FileNotFoundError(f"path not found: {path}")
        return list(self._entries)

    def read(self, path: str, *, format: str) -> bytearray:  # noqa: A002, ARG002 — mirrors SDK sig
        self.read_paths.append(path)
        # The real SDK returns a bytearray for format="bytes".
        return bytearray(self._read_payloads.get(path, b""))


class _Execution:
    """Minimal E2B ``Execution`` stand-in (no error, configurable stdout)."""

    def __init__(self, stdout: str = "") -> None:
        class _Logs:
            def __init__(self, out: str) -> None:
                self.stdout = [out] if out else []
                self.stderr: list[str] = []

        self.logs = _Logs(stdout)
        self.error = None


class _FakeSandbox:
    """Stand-in for the E2B ``Sandbox`` exposing ``files`` + ``run_code``."""

    def __init__(self, files: _FakeFiles, stdout: str = "done") -> None:
        self.files = files
        self._stdout = stdout
        self.run_code_calls: list[str] = []

    def run_code(self, code: str, *, timeout: float) -> _Execution:  # noqa: ARG002
        self.run_code_calls.append(code)
        return _Execution(self._stdout)

    def kill(self) -> None: ...


_PNG = "/workspace/out/chart.png"
_CSV = "/workspace/out/data.csv"


def _png_csv_files() -> _FakeFiles:
    entries = [
        _EntryInfo(name="chart.png", type=_FileType.FILE, path=_PNG, size=66),
        _EntryInfo(name="data.csv", type=_FileType.FILE, path=_CSV, size=8),
    ]
    return _FakeFiles(entries, read_payloads={_PNG: b"\x89PNG", _CSV: b"a,b\n1,2\n"})


def test_produced_png_becomes_image_produced_file() -> None:
    """A produced PNG surfaces as a produced_file with media_type image/png."""
    fake = _FakeSandbox(_png_csv_files())
    sandbox = HostedSandbox()

    result = sandbox._run_and_marshal(  # noqa: SLF001
        fake,  # type: ignore[arg-type]
        "open('/workspace/out/chart.png','wb').write(b'x')",
        timeout_s=5.0,
        input_files=[],
        limits=ResourceLimits(),
    )

    assert result.outcome == "ok"
    by_path = {f.path: f for f in result.produced_files}
    assert set(by_path) == {"chart.png", "data.csv"}
    # The image MUST carry an image/* media type so the frontend renders it
    # inline (classifyArtifact / rendererKindFor key on media_type.startsWith).
    assert by_path["chart.png"].media_type == "image/png"
    assert by_path["data.csv"].media_type == "text/csv"
    # Paths are workspace-relative (never absolute) per the SandboxFile contract.
    assert all(not f.path.startswith("/") for f in result.produced_files)
    assert by_path["chart.png"].size_bytes == 66
    assert not result.truncated_files


def test_listing_uses_recursive_depth_and_skips_dirs() -> None:
    """Recursive listing surfaces charts/<id>.png; DIR entries are skipped."""
    nested = "/workspace/out/charts/sales.png"
    entries = [
        _EntryInfo(name="charts", type=_FileType.DIR, path="/workspace/out/charts", size=0),
        _EntryInfo(name="sales.png", type=_FileType.FILE, path=nested, size=5),
        _EntryInfo(name="top.png", type=_FileType.FILE, path="/workspace/out/top.png", size=4),
    ]
    fake = _FakeSandbox(_FakeFiles(entries, read_payloads={nested: b"\x89PNG2"}))
    sandbox = HostedSandbox()

    result = sandbox._run_and_marshal(  # noqa: SLF001
        fake, "x", timeout_s=5.0, input_files=[], limits=ResourceLimits()
    )

    paths = {f.path for f in result.produced_files}
    # The charts/ prefix is load-bearing (D-17-X chart-vs-image discriminator).
    assert paths == {"charts/sales.png", "top.png"}
    # Recursion depth must be > 1 so the sub-dir is reached.
    assert fake.files.list_calls
    _path, depth = fake.files.list_calls[0]
    assert depth is not None
    assert depth > 1


def test_missing_out_dir_yields_no_produced_files() -> None:
    """A run that wrote nothing (no out-dir) yields empty produced_files, not an error."""
    fake = _FakeSandbox(_FakeFiles([]))  # list() raises (missing dir)
    sandbox = HostedSandbox()

    result = sandbox._run_and_marshal(  # noqa: SLF001
        fake, "print('hi')", timeout_s=5.0, input_files=[], limits=ResourceLimits()
    )

    assert result.outcome == "ok"
    assert result.produced_files == ()
    assert not result.truncated_files


def test_per_file_size_cap_skips_oversize_and_marks_truncated() -> None:
    """A file over max_produced_file_mb is skipped and the run marked truncated."""
    big = "/workspace/out/huge.bin"
    small = "/workspace/out/ok.png"
    entries = [
        _EntryInfo(name="huge.bin", type=_FileType.FILE, path=big, size=3 * 1024 * 1024),
        _EntryInfo(name="ok.png", type=_FileType.FILE, path=small, size=10),
    ]
    fake = _FakeSandbox(_FakeFiles(entries, read_payloads={small: b"\x89PNG"}))
    sandbox = HostedSandbox()

    result = sandbox._run_and_marshal(  # noqa: SLF001
        fake,
        "x",
        timeout_s=5.0,
        input_files=[],
        limits=ResourceLimits(max_produced_file_mb=1),
    )

    paths = {f.path for f in result.produced_files}
    assert paths == {"ok.png"}
    assert result.truncated_files


def test_count_cap_stops_enumeration_and_marks_truncated() -> None:
    """More files than max_produced_files truncates the list."""
    entries = [
        _EntryInfo(
            name=f"f{i}.png",
            type=_FileType.FILE,
            path=f"/workspace/out/f{i}.png",
            size=4,
        )
        for i in range(5)
    ]
    fake = _FakeSandbox(_FakeFiles(entries))
    sandbox = HostedSandbox()

    result = sandbox._run_and_marshal(  # noqa: SLF001
        fake,
        "x",
        timeout_s=5.0,
        input_files=[],
        limits=ResourceLimits(max_produced_files=2),
    )

    assert len(result.produced_files) == 2
    assert result.truncated_files


def test_produced_files_discovered_even_on_user_error() -> None:
    """A partial-success run that errored after writing a chart still surfaces it."""
    fake = _FakeSandbox(_png_csv_files())

    class _Err:
        name = "ValueError"
        value = "boom"

    def _run_code(code: str, *, timeout: float) -> _Execution:  # noqa: ARG001
        ex = _Execution("partial")
        ex.error = _Err()  # type: ignore[assignment]
        return ex

    fake.run_code = _run_code  # type: ignore[assignment, method-assign]
    sandbox = HostedSandbox()

    result = sandbox._run_and_marshal(  # noqa: SLF001
        fake, "x", timeout_s=5.0, input_files=[], limits=ResourceLimits()
    )

    assert result.outcome == "error"
    # The chart written before the error is still surfaced.
    assert {f.path for f in result.produced_files} == {"chart.png", "data.csv"}


@pytest.mark.asyncio
async def test_read_produced_file_bytes_handles_bytearray_return() -> None:
    """read_produced_file_bytes coerces the SDK's bytearray return to bytes."""
    fake = _FakeSandbox(_png_csv_files())
    sandbox = HostedSandbox()
    sandbox._sessions["alice:c1"] = fake  # type: ignore[assignment]  # noqa: SLF001

    data = await sandbox.read_produced_file_bytes("alice:c1", "chart.png")

    assert data == b"\x89PNG"
    assert isinstance(data, bytes)
    assert fake.files.read_paths == [f"{_HOSTED_WORKSPACE_OUT}/chart.png"]

"""B2: deprecated-skill alias resolution (D-24-3, D-24-9)."""

from __future__ import annotations

from collections.abc import Iterator  # noqa: TC003 — runtime fixture annotation

import pytest
from loguru import logger
from persona.skills.aliases import SKILL_ALIASES, resolve_skill_aliases

_OLD_NAMES = [
    "docx_generation",
    "pdf_generation",
    "pptx_generation",
    "xlsx_generation",
    "document_drafting",
]


@pytest.fixture
def alias_logs() -> Iterator[list[str]]:
    """Capture loguru records emitted during the test (house pattern: sink)."""
    captured: list[str] = []
    sink_id = logger.add(captured.append, level="INFO", format="{message} {extra}")
    yield captured
    logger.remove(sink_id)


def test_every_old_name_maps_to_document_generation() -> None:
    for old in _OLD_NAMES:
        assert SKILL_ALIASES[old][0] == "document_generation"


@pytest.mark.parametrize("old", _OLD_NAMES)
def test_resolve_rewrites_each_old_name(old: str) -> None:
    assert resolve_skill_aliases([old]) == ["document_generation"]


def test_non_alias_names_pass_through_unchanged() -> None:
    assert resolve_skill_aliases(["web_research", "data_analysis"]) == [
        "web_research",
        "data_analysis",
    ]


def test_declared_order_preserved_and_deduped() -> None:
    # docx + pdf both fold to document_generation → one entry, in place.
    assert resolve_skill_aliases(
        ["web_research", "docx_generation", "pdf_generation", "data_analysis"]
    ) == ["web_research", "document_generation", "data_analysis"]


def test_alias_plus_explicit_target_dedup() -> None:
    assert resolve_skill_aliases(["document_generation", "docx_generation"]) == [
        "document_generation",
    ]


def test_resolution_emits_info_log(alias_logs: list[str]) -> None:
    resolve_skill_aliases(["docx_generation"])
    assert any("resolved deprecated skill alias" in line for line in alias_logs)
    assert any("docx_generation" in line for line in alias_logs)

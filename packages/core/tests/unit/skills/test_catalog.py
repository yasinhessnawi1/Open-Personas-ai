"""B4: skills.toml catalog + collection: expansion (D-24-6)."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003 — runtime fixture annotation

import pytest
from persona.errors import SkillNameCollisionError
from persona.skills import BUILTIN_ROOT, SkillScanner
from persona.skills.catalog import (
    BUILTIN_CATALOG,
    SkillCatalog,
    expand_collections,
    load_catalog,
)

_CUSTOM = SkillCatalog(
    skills={"a": "builtin/a", "b": "builtin/b", "c": "builtin/c"},
    collections={"pair": ("a", "b"), "single": ("c",)},
)


def test_bundled_catalog_lists_the_live_skills_and_collections() -> None:
    assert set(BUILTIN_CATALOG.skills) == {
        "web_research",
        "data_analysis",
        "document_generation",
        "code_review",
    }
    assert BUILTIN_CATALOG.collections["document"] == ("document_generation",)
    assert BUILTIN_CATALOG.collections["research"] == ("web_research", "data_analysis")


def test_expand_collection_ref_to_members() -> None:
    assert expand_collections(["collection:pair"], _CUSTOM) == ["a", "b"]
    assert expand_collections(["collection:single"], _CUSTOM) == ["c"]


def test_expand_skill_prefix_strips_to_bare_id() -> None:
    assert expand_collections(["skill:a", "b"], _CUSTOM) == ["a", "b"]


def test_expand_dedups_across_collection_and_bare() -> None:
    # pair = (a, b); declaring pair then a → a not duplicated.
    assert expand_collections(["collection:pair", "a"], _CUSTOM) == ["a", "b"]


def test_unknown_collection_is_skipped_not_fatal() -> None:
    assert expand_collections(["collection:nope", "a"], _CUSTOM) == ["a"]


def test_bare_names_pass_through_unchanged() -> None:
    assert expand_collections(["web_research", "data_analysis"]) == [
        "web_research",
        "data_analysis",
    ]


def test_collection_name_clashing_with_skill_id_fails_loud(tmp_path: Path) -> None:
    toml = tmp_path / "catalog.toml"
    toml.write_text(
        '[skill.web_research]\npath = "builtin/web_research"\n'
        '[collection.web_research]\nmembers = ["web_research"]\n',
        encoding="utf-8",
    )
    with pytest.raises(SkillNameCollisionError) as exc:
        load_catalog(toml)
    assert exc.value.context["name"] == "web_research"


def test_scanner_resolves_collection_ref_end_to_end() -> None:
    scanner = SkillScanner([BUILTIN_ROOT])
    specs = scanner.scan(["collection:research"])
    assert {s.name for s in specs} == {"web_research", "data_analysis"}


def test_scanner_collection_document_resolves_to_unified_skill() -> None:
    scanner = SkillScanner([BUILTIN_ROOT])
    [spec] = scanner.scan(["collection:document"])
    assert spec.name == "document_generation"


def test_collection_then_deprecated_alias_dedup() -> None:
    # collection:document → document_generation; docx_generation → same → dedup.
    scanner = SkillScanner([BUILTIN_ROOT])
    specs = scanner.scan(["collection:document", "docx_generation"])
    assert [s.name for s in specs] == ["document_generation"]

"""A3: the unified ``document_generation`` builtin skill ↔ registry consistency.

Guards against drift between the registry (code) and the bundled skill data
(SKILL.md front matter + supplements/ + templates/).
"""

from __future__ import annotations

from persona.skills import BUILTIN_ROOT, SkillScanner
from persona.skills._frontmatter import parse_skill_markdown
from persona.skills.document_generation import (
    FORMAT_HANDLERS,
    supported_formats,
    supported_templates,
)

_SKILL_DIR = BUILTIN_ROOT / "document_generation"


def test_scanner_discovers_document_generation() -> None:
    specs = SkillScanner([BUILTIN_ROOT]).scan(["document_generation"])
    assert len(specs) == 1
    spec = specs[0]
    assert spec.name == "document_generation"
    assert spec.description
    assert spec.when_to_use
    assert spec.tools_required == ["code_execution"]
    assert spec.content  # body is non-empty
    assert spec.content_token_count > 0


def test_skill_md_format_enum_matches_registry() -> None:
    meta, _ = parse_skill_markdown(_SKILL_DIR / "SKILL.md")
    enum = meta["metadata"]["parameters"]["properties"]["format"]["enum"]
    assert sorted(enum) == list(supported_formats())


def test_skill_md_template_enum_matches_registry() -> None:
    meta, _ = parse_skill_markdown(_SKILL_DIR / "SKILL.md")
    enum = meta["metadata"]["parameters"]["properties"]["template"]["enum"]
    assert sorted(enum) == list(supported_templates())


def test_every_declared_supplement_topic_has_a_bundled_file() -> None:
    supplements = _SKILL_DIR / "supplements"
    for fmt, handler in FORMAT_HANDLERS.items():
        for topic in handler.supplement_topics:
            path = supplements / f"{fmt}-{topic}.md"
            assert path.is_file(), f"missing supplement {path.name}"


def test_every_registered_template_has_a_bundled_file() -> None:
    templates = _SKILL_DIR / "templates"
    for template_id in supported_templates():
        path = templates / f"{template_id}.md"
        assert path.is_file(), f"missing template {path.name}"
        assert "{{" in path.read_text(), f"template {path.name} has no placeholders"


def test_text_formats_bundle_no_supplements() -> None:
    # md / txt declare no topics; nothing prefixed md-/txt- should exist.
    supplements = _SKILL_DIR / "supplements"
    stray = [p.name for p in supplements.glob("md-*.md")]
    stray += [p.name for p in supplements.glob("txt-*.md")]
    assert stray == []

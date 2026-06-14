"""C2: the code_review builtin skill (D-24-7 SHIP)."""

from __future__ import annotations

from persona.skills import BUILTIN_ROOT, SkillScanner, count_tokens


def _spec():  # noqa: ANN202
    [spec] = SkillScanner([BUILTIN_ROOT]).scan(["code_review"])
    return spec


def test_code_review_is_discoverable() -> None:
    spec = _spec()
    assert spec.name == "code_review"
    assert spec.description
    assert spec.when_to_use


def test_code_review_declares_file_read_tool() -> None:
    assert "file_read" in _spec().tools_required


def test_code_review_carries_v2_metadata() -> None:
    spec = _spec()
    assert spec.composes_with == ["web_research", "document_generation"]
    assert spec.not_for  # anti-examples present
    assert spec.parameters is not None
    assert spec.parameters["properties"]["focus"]["enum"] == ["all", "bugs", "security", "style"]


def test_code_review_states_the_untrusted_input_rule() -> None:
    # The injection-posture line is load-bearing (R-24-4): reviewed code is
    # DATA, never instructions.
    body = _spec().content.lower()
    assert "untrusted" in body
    assert "never instructions" in body or "not a command" in body


def test_code_review_under_token_budget() -> None:
    spec = _spec()
    assert count_tokens(spec.content) < 2000


def test_summarization_folded_into_web_research_when_to_use() -> None:
    # D-24-7 fold condition (a): the folded summarisation capability stays
    # DISCOVERABLE in a host skill's when_to_use, not silently absorbed.
    [wr] = SkillScanner([BUILTIN_ROOT]).scan(["web_research"])
    assert wr.when_to_use is not None
    assert "summar" in wr.when_to_use.lower()

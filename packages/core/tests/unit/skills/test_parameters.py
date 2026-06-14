"""B1b: parameters validation engine (D-24-8)."""

from __future__ import annotations

from pathlib import Path

import pytest
from persona.errors import SkillArgumentValidationError
from persona.schema.skills import SkillSpec
from persona.skills.parameters import build_parameter_model, validate_parameters

_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["format"],
    "properties": {
        "format": {"type": "string", "enum": ["docx", "pdf", "md"]},
        "template": {"type": "string"},
        "content_spec": {"type": "object"},
        "copies": {"type": "integer"},
    },
}


def _spec(**kw: object) -> SkillSpec:
    return SkillSpec(name="doc", description="d", path=Path("/tmp/doc"), **kw)  # type: ignore[arg-type]


def test_no_schema_is_a_noop() -> None:
    validate_parameters(_spec(), {"anything": 1})  # no parameters → accept


def test_valid_args_pass() -> None:
    spec = _spec(parameters=_SCHEMA)
    validate_parameters(spec, {"format": "docx", "template": "memo"})
    validate_parameters(spec, {"format": "md"})


def test_missing_required_format_raises() -> None:
    spec = _spec(parameters=_SCHEMA)
    with pytest.raises(SkillArgumentValidationError) as exc:
        validate_parameters(spec, {"template": "memo"})
    assert exc.value.context["skill"] == "doc"
    assert "format" in exc.value.context["errors"]


def test_enum_violation_raises() -> None:
    spec = _spec(parameters=_SCHEMA)
    with pytest.raises(SkillArgumentValidationError):
        validate_parameters(spec, {"format": "odt"})


def test_extra_property_rejected_by_additionalproperties_false() -> None:
    spec = _spec(parameters=_SCHEMA)
    with pytest.raises(SkillArgumentValidationError):
        validate_parameters(spec, {"format": "docx", "bogus": "x"})


def test_wrong_type_rejected() -> None:
    spec = _spec(parameters=_SCHEMA)
    with pytest.raises(SkillArgumentValidationError):
        validate_parameters(spec, {"format": "docx", "copies": "two"})


def test_build_model_marks_required_and_optional() -> None:
    model = build_parameter_model("doc", _SCHEMA)
    assert model.model_fields["format"].is_required()
    assert not model.model_fields["template"].is_required()

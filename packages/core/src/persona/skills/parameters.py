"""Strict ``use_skill`` argument validation against a skill's ``parameters`` (D-24-8).

JSON Schema (2020-12) is the on-disk *interface*; a frozen ``extra="forbid"``
Pydantic model built from it at call time is the validation *engine* — no new
dependency (Pydantic is a base dep; there is deliberately **no** ``jsonschema``
library, per D-24-8). Only the subset of JSON Schema the skill ``parameters``
blocks actually use is translated: ``type: object`` with typed ``properties``
(``string`` / ``integer`` / ``number`` / ``boolean`` / ``object`` / ``array``,
optional ``enum``), a ``required`` list, and ``additionalProperties`` (default
forbid). Anything outside the subset degrades to ``Any`` (accepted) rather than
raising — authoring errors surface as scan-time problems, not validation crashes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, ValidationError, create_model

from persona.errors import SkillArgumentValidationError

if TYPE_CHECKING:
    from persona.schema.skills import SkillSpec

__all__ = ["build_parameter_model", "validate_parameters"]

# JSON Schema primitive ``type`` → Python type used to build the validator.
_PRIMITIVES: dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "object": dict[str, Any],
    "array": list[Any],
}


def _python_type(prop_schema: dict[str, Any]) -> Any:  # noqa: ANN401 — returns a dynamic type object (str/int/Literal/dict/Any) for create_model
    """Map one JSON-Schema property to a Python type for the Pydantic model."""
    enum = prop_schema.get("enum")
    if isinstance(enum, list) and enum:
        # Literal over the enum members (runtime values; the function returns
        # Any so the dynamic Literal subscription is accepted).
        return Literal[tuple(enum)]
    json_type = prop_schema.get("type")
    if isinstance(json_type, str):
        return _PRIMITIVES.get(json_type, Any)
    return Any


def build_parameter_model(name: str, schema: dict[str, Any]) -> type[BaseModel]:
    """Compile a skill ``parameters`` JSON Schema into a strict Pydantic model.

    Args:
        name: The skill name (used for the generated model's class name).
        schema: The skill's ``parameters`` JSON Schema (``type: object``).

    Returns:
        A frozen Pydantic model. ``additionalProperties: false`` (the default)
        maps to ``extra="forbid"``; required properties are required fields,
        the rest optional with a ``None`` default.
    """
    properties = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    forbid = schema.get("additionalProperties", False) is False
    fields: dict[str, tuple[Any, Any]] = {}
    for field_name, prop in properties.items():
        prop_dict = prop if isinstance(prop, dict) else {}
        py_type = _python_type(prop_dict)
        if field_name in required:
            fields[field_name] = (py_type, ...)
        else:
            fields[field_name] = (Optional[py_type], None)  # noqa: UP045 — dynamic
    config = ConfigDict(extra="forbid" if forbid else "allow", frozen=True)
    # create_model is dynamically typed; the **fields splat defeats mypy's
    # field-definition checking — acceptable for this bounded translator.
    return create_model(  # type: ignore[call-overload, no-any-return]
        f"{name}_Params",
        __config__=config,
        **fields,
    )


def validate_parameters(spec: SkillSpec, args: dict[str, Any]) -> None:
    """Validate ``args`` against ``spec.parameters``; raise on mismatch.

    No-op when the skill declares no ``parameters`` schema (the common case —
    most skills take no call arguments).

    Args:
        spec: The activated skill.
        args: The ``parameters`` dict the model passed to ``use_skill``.

    Raises:
        SkillArgumentValidationError: ``args`` violate the declared schema;
            ``context`` names the skill and the joined validation messages.
    """
    schema = spec.parameters
    if not schema:
        return
    model = build_parameter_model(spec.name, schema)
    try:
        model.model_validate(args)
    except ValidationError as exc:
        messages = "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors()
        )
        raise SkillArgumentValidationError(
            "invalid skill parameters",
            context={"skill": spec.name, "errors": messages},
        ) from exc

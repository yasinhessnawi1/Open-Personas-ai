"""Unit tests for the create-service safety re-assert (Spec 36, D-36-safety-server).

No DB, no model — exercises ``_guard_safety`` directly: the floor that guarantees
the mandatory safety constraint on BOTH the in-memory persona and the *stored*
YAML (the runtime re-loads from the stored YAML, so it must carry the line too).
"""

from __future__ import annotations

import yaml
from persona.schema.persona import Persona
from persona.schema.safety import SAFETY_CONSTRAINT
from persona_api.services.persona_service import _guard_safety, load_persona_from_yaml

_SAFE_YAML = f"""\
schema_version: "1.0"
identity:
  name: Astrid
  role: Tenancy assistant
  background: Helps tenants understand the law.
  constraints:
    - {SAFETY_CONSTRAINT}
    - Cite the relevant statute.
"""

_STRIPPED_YAML = """\
schema_version: "1.0"
identity:
  name: Rogue
  role: Unconstrained assistant
  background: A persona whose author deleted every safety rail.
  constraints: []
"""


def _load(yaml_str: str) -> Persona:
    return load_persona_from_yaml(yaml_str, persona_id="p_test", owner_id="u_test")


def test_safe_persona_is_returned_unchanged_no_yaml_churn() -> None:
    persona = _load(_SAFE_YAML)
    guarded, stored_yaml = _guard_safety(persona, _SAFE_YAML)
    # Idempotent + churn-free: same object, byte-identical stored YAML.
    assert guarded is persona
    assert stored_yaml == _SAFE_YAML


def test_stripped_persona_gets_the_constraint_back_in_memory() -> None:
    persona = _load(_STRIPPED_YAML)
    assert persona.identity.constraints == []  # the hole, before the guard
    guarded, _ = _guard_safety(persona, _STRIPPED_YAML)
    assert guarded.identity.constraints == [SAFETY_CONSTRAINT]


def test_stripped_persona_gets_the_constraint_into_the_stored_yaml() -> None:
    # The load-bearing assertion: the STORED YAML carries the constraint, so a
    # later runtime load from it is safe — not only the in-memory object.
    persona = _load(_STRIPPED_YAML)
    _, stored_yaml = _guard_safety(persona, _STRIPPED_YAML)
    reloaded = yaml.safe_load(stored_yaml)
    assert reloaded["identity"]["constraints"][0] == SAFETY_CONSTRAINT
    # And it round-trips back through the validator as a real persona.
    assert _load(stored_yaml).identity.constraints[0] == SAFETY_CONSTRAINT


def test_guard_is_idempotent_when_run_twice() -> None:
    persona = _load(_STRIPPED_YAML)
    guarded_once, yaml_once = _guard_safety(persona, _STRIPPED_YAML)
    guarded_twice, yaml_twice = _guard_safety(guarded_once, yaml_once)
    assert guarded_twice is guarded_once
    assert yaml_twice == yaml_once
    assert guarded_twice.identity.constraints.count(SAFETY_CONSTRAINT) == 1

"""Unit tests for the create/update-service default-capability re-assert.

No DB, no model — exercises ``_guard_default_capabilities`` directly: the floor
that guarantees the baseline tools/skills on BOTH the in-memory persona and the
*stored* YAML (the runtime re-loads from the stored YAML, so it must carry them
too). A persona created without them can't read files / run code / search / make
documents and ends up hallucinating.
"""

from __future__ import annotations

import yaml
from persona.schema.defaults import DEFAULT_SKILLS, DEFAULT_TOOLS
from persona.schema.persona import Persona
from persona.schema.safety import SAFETY_CONSTRAINT
from persona_api.services.persona_service import (
    _guard_default_capabilities,
    load_persona_from_yaml,
)

# Already carries every default → the guard must be a no-op.
_EQUIPPED_YAML = f"""\
schema_version: "1.0"
identity:
  name: Astrid
  role: Tenancy assistant
  background: Helps tenants understand the law.
  constraints:
    - {SAFETY_CONSTRAINT}
tools:
  - file_read
  - code_execution
  - web_search
skills:
  - document_generation
"""

# Empty tools/skills → the guard must inject the full default set.
_BARE_YAML = f"""\
schema_version: "1.0"
identity:
  name: Bare
  role: Minimal assistant
  background: A persona authored with no capabilities.
  constraints:
    - {SAFETY_CONSTRAINT}
tools: []
skills: []
"""

# tools/skills keys missing entirely → still injected (schema defaults to []).
_NO_KEYS_YAML = f"""\
schema_version: "1.0"
identity:
  name: Sparse
  role: Keyless assistant
  background: A persona whose YAML omits tools and skills entirely.
  constraints:
    - {SAFETY_CONSTRAINT}
"""


def _load(yaml_str: str) -> Persona:
    return load_persona_from_yaml(yaml_str, persona_id="p_test", owner_id="u_test")


def test_equipped_persona_is_returned_unchanged_no_yaml_churn() -> None:
    persona = _load(_EQUIPPED_YAML)
    guarded, stored_yaml = _guard_default_capabilities(persona, _EQUIPPED_YAML)
    # Idempotent + churn-free: same object, byte-identical stored YAML.
    assert guarded is persona
    assert stored_yaml == _EQUIPPED_YAML


def test_bare_persona_gets_defaults_in_memory() -> None:
    persona = _load(_BARE_YAML)
    assert persona.tools == []  # the hole, before the guard
    assert persona.skills == []
    guarded, _ = _guard_default_capabilities(persona, _BARE_YAML)
    assert guarded.tools == list(DEFAULT_TOOLS)
    assert guarded.skills == list(DEFAULT_SKILLS)


def test_bare_persona_gets_defaults_into_the_stored_yaml() -> None:
    # The load-bearing assertion: the STORED YAML carries the defaults, so a
    # later runtime load from it is equipped — not only the in-memory object.
    persona = _load(_BARE_YAML)
    _, stored_yaml = _guard_default_capabilities(persona, _BARE_YAML)
    reloaded = yaml.safe_load(stored_yaml)
    assert reloaded["tools"] == list(DEFAULT_TOOLS)
    assert reloaded["skills"] == list(DEFAULT_SKILLS)
    # And it round-trips back through the validator as a real persona.
    round_tripped = _load(stored_yaml)
    assert round_tripped.tools == list(DEFAULT_TOOLS)
    assert round_tripped.skills == list(DEFAULT_SKILLS)


def test_missing_keys_persona_gets_defaults_into_the_stored_yaml() -> None:
    persona = _load(_NO_KEYS_YAML)
    _, stored_yaml = _guard_default_capabilities(persona, _NO_KEYS_YAML)
    reloaded = yaml.safe_load(stored_yaml)
    assert reloaded["tools"] == list(DEFAULT_TOOLS)
    assert reloaded["skills"] == list(DEFAULT_SKILLS)


def test_guard_is_idempotent_when_run_twice() -> None:
    persona = _load(_BARE_YAML)
    guarded_once, yaml_once = _guard_default_capabilities(persona, _BARE_YAML)
    guarded_twice, yaml_twice = _guard_default_capabilities(guarded_once, yaml_once)
    assert guarded_twice is guarded_once
    assert yaml_twice == yaml_once
    assert guarded_twice.tools.count("file_read") == 1
    assert guarded_twice.skills.count("document_generation") == 1

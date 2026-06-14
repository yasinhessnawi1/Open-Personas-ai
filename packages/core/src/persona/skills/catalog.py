"""Lightweight skill catalog + ``collection:`` expansion (Spec 24, D-24-6).

Loads the bundled ``catalog.toml`` (a declarative index of builtin skills +
named collections) and expands a persona's ``skills`` list under the uniform
``kind:ref`` grammar:

* ``collection:<name>`` → the collection's members, in catalog order;
* ``skill:<id>`` → ``<id>`` (the explicit form);
* a bare ``<id>`` → unchanged (the ergonomic default).

This is the **precursor** to the deferred federated registry (architecture
§9.3), not the registry: resolution is 100% local, zero-network. ``tomllib``
(stdlib) parses the file — no new dependency. Name clashes between a collection
and a skill id fail loud at load (``SkillNameCollisionError``, per R-24-1);
unknown collection refs and unknown collection members warn-and-skip.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from persona.errors import SkillNameCollisionError
from persona.logging import get_logger

__all__ = [
    "BUILTIN_CATALOG",
    "CATALOG_PATH",
    "COLLECTION_PREFIX",
    "SKILL_PREFIX",
    "SkillCatalog",
    "expand_collections",
    "load_catalog",
]

_logger = get_logger("skills.catalog")

#: Bundled catalog file, shipped as package data alongside the skill dirs.
CATALOG_PATH: Path = Path(__file__).parent / "catalog.toml"

COLLECTION_PREFIX = "collection:"
SKILL_PREFIX = "skill:"


@dataclass(frozen=True)
class SkillCatalog:
    """Parsed ``catalog.toml`` — skill ids + named collections.

    Attributes:
        skills: Mapping of skill id → relative path (under the skills package).
        collections: Mapping of collection name → ordered member skill ids.
    """

    skills: dict[str, str]
    collections: dict[str, tuple[str, ...]]


def load_catalog(path: Path = CATALOG_PATH) -> SkillCatalog:
    """Parse a ``catalog.toml`` into a :class:`SkillCatalog`.

    Args:
        path: The catalog file (defaults to the bundled one).

    Returns:
        The parsed catalog.

    Raises:
        SkillNameCollisionError: a collection name duplicates a skill id
            (ambiguous under the uniform ``kind:ref`` scheme).
    """
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    skills = {sid: str(entry.get("path", "")) for sid, entry in data.get("skill", {}).items()}
    collections: dict[str, tuple[str, ...]] = {}
    for name, entry in data.get("collection", {}).items():
        if name in skills:
            raise SkillNameCollisionError(
                "collection name duplicates a skill id",
                context={"name": name},
            )
        members = tuple(str(m) for m in entry.get("members", []))
        for member in members:
            if member not in skills:
                _logger.warning(
                    "skill collection references an unknown skill",
                    collection=name,
                    member=member,
                )
        collections[name] = members
    return SkillCatalog(skills=skills, collections=collections)


#: The bundled catalog, loaded once. Read-only configuration (mirrors
#: ``BUILTIN_ROOT``); never mutated at runtime.
BUILTIN_CATALOG: SkillCatalog = load_catalog()


def expand_collections(
    declared: list[str],
    catalog: SkillCatalog = BUILTIN_CATALOG,
) -> list[str]:
    """Expand ``collection:`` / ``skill:`` refs in a declared skill list.

    Args:
        declared: The persona's raw ``skills: [...]`` list.
        catalog: The catalog to resolve against (defaults to the bundled one).

    Returns:
        The expanded, de-duplicated skill-id list (declared order preserved;
        collection members inserted in catalog order). Unknown collections and
        unknown members are skipped with a WARNING — a persona never fails to
        load because one collection ref is stale.
    """
    out: list[str] = []
    seen: set[str] = set()

    def _add(skill_id: str) -> None:
        if skill_id not in seen:
            seen.add(skill_id)
            out.append(skill_id)

    for item in declared:
        if item.startswith(COLLECTION_PREFIX):
            name = item[len(COLLECTION_PREFIX) :]
            members = catalog.collections.get(name)
            if members is None:
                _logger.warning(
                    "unknown skill collection referenced",
                    collection=name,
                    available=", ".join(sorted(catalog.collections)),
                )
                continue
            for member in members:
                if member in catalog.skills:
                    _add(member)
        elif item.startswith(SKILL_PREFIX):
            _add(item[len(SKILL_PREFIX) :])
        else:
            _add(item)
    return out

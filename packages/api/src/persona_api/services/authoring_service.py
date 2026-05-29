"""LLM-assisted persona authoring (spec 08, T07, §5.1 / §6.3 / D-08-6).

Turns a natural-language description into a draft v1.0 persona YAML by prompting
a frontier-tier model. The backend is injected (the route resolves it from the
TierRegistry, T10), so this service is decoupled from provider wiring and
testable with a scripted backend.

The v0.1 prompt is deliberately compact; the architecture (§6.3) notes the
production prompt is a multi-day effort with 20+ test descriptions — that
tuning is post-this-spec. What T07 delivers is the working seam: description →
frontier model → validated v1.0 YAML (or a clear error if the model's output
doesn't validate).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import yaml
from persona.errors import PersonaError
from persona.schema.conversation import ConversationMessage
from persona.schema.persona import Persona
from pydantic import ValidationError

if TYPE_CHECKING:
    from persona.backends import ChatBackend

__all__ = ["author_persona_yaml"]

_SYSTEM_PROMPT = """\
You are a persona authoring assistant for the Open Persona platform. Given a \
short natural-language description, produce a single valid persona YAML document \
conforming to schema_version "1.0". Output ONLY the YAML — no prose, no fences.

The YAML must have this shape:

schema_version: "1.0"
identity:
  name: <short name>
  role: <one-line role>
  background: |
    <2-4 sentences>
  language_default: en
  constraints:
    - <constraint>
self_facts:
  - fact: <fact about the persona's scope/abilities>
    confidence: 1.0
worldview:
  - claim: <a belief or fact the persona holds>
    domain: <topic>
    epistemic: belief        # one of: fact | belief | hypothesis | contested
    confidence: 0.9
    valid_time: always
tools: []
skills: []

Keep it concise: 2-4 self_facts, 1-3 worldview claims, 2-4 constraints. Do not \
invent a persona_id or owner_id — those are assigned by the system.
"""


async def author_persona_yaml(backend: ChatBackend, description: str) -> str:
    """Generate a validated v1.0 persona YAML from a description.

    Args:
        backend: The frontier-tier chat backend (injected; §6.3).
        description: The user's natural-language persona description.

    Returns:
        A YAML string that parses + validates as a v1.0 :class:`Persona`
        (with placeholder id/owner the create endpoint will overwrite).

    Raises:
        PersonaError: The model's output is not valid YAML or does not validate
            against the v1.0 schema (so the endpoint returns a clear error
            rather than a malformed draft).
    """
    now = datetime.now(UTC)
    messages = [
        ConversationMessage(role="system", content=_SYSTEM_PROMPT, created_at=now),
        ConversationMessage(role="user", content=description, created_at=now),
    ]
    response = await backend.chat(messages, temperature=0.0)
    draft = _strip_fences(response.content)

    # Validate the draft so we never hand back a malformed persona. Use
    # placeholder id/owner (the create endpoint assigns the real ones).
    try:
        raw = yaml.safe_load(draft)
    except yaml.YAMLError as exc:
        raise PersonaError(
            "authoring model produced invalid YAML", context={"reason": str(exc)[:200]}
        ) from exc
    if not isinstance(raw, dict):
        raise PersonaError("authoring model output was not a YAML mapping")
    raw.setdefault("persona_id", "draft")
    raw.setdefault("owner_id", "draft")
    try:
        Persona.model_validate(raw)
    except ValidationError as exc:
        raise PersonaError(
            "authoring model output failed v1.0 schema validation",
            context={"errors": str(exc.errors(include_url=False))[:400]},
        ) from exc
    return draft


def _strip_fences(text: str) -> str:
    """Remove a leading/trailing ``` fence if the model added one anyway."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        # drop the first fence line (``` or ```yaml) and a trailing fence
        body = lines[1:]
        if body and body[-1].strip().startswith("```"):
            body = body[:-1]
        return "\n".join(body).strip()
    return stripped

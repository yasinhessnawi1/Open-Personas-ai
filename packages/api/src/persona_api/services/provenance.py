"""Synthetic-media provenance → Art. 50 disclosure derivation (Spec R3, R3-D-4).

A single, pure derivation reused by every disclosure surface (the persona detail
avatar, the workspace-artifact list) so the recipient-facing "AI-generated"
signal is **derived from the stored structural signal, never guessed** — the EU
AI Act Art. 50 invariant. The structural signal is the canonical ``source``
string written at persist time (``'generated'`` / ``'uploaded'`` for avatars;
``WorkspaceArtifactMetadata.source`` for workspace artifacts). This module turns
it into the tri-state disclosure boolean; it does NOT duplicate or re-derive the
structural signal (R3-D-4: ride the existing field, add only the label).
"""

from __future__ import annotations

#: The canonical "this was AI-generated" provenance value (avatars + sidecars).
_GENERATED = "generated"
#: The canonical "a user supplied these bytes" provenance value.
_UPLOADED = "uploaded"


def ai_generated_from_source(source: str | None) -> bool | None:
    """Derive the Art. 50 ``ai_generated`` disclosure from a stored provenance signal.

    Args:
        source: The stored structural provenance — ``'generated'``, ``'uploaded'``,
            or ``None`` (unknown: a legacy row/artifact that predates the signal,
            R3-D-5).

    Returns:
        ``True`` when the bytes are AI-/system-generated, ``False`` when a user
        uploaded them, ``None`` when provenance is unknown (no claim is made — an
        honest "unknown", never a guess).
    """
    if source == _GENERATED:
        return True
    if source == _UPLOADED:
        return False
    return None


# Avatar-surface alias — same derivation, named for the call site's clarity.
avatar_ai_generated_from_source = ai_generated_from_source

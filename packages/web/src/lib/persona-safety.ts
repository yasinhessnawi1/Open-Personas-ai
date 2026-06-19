/**
 * The mandatory persona safety constraint + the client-side re-assert guard,
 * the web mirror of the Python source of truth in
 * `packages/core/src/persona/schema/safety.py` (Spec 36, D-36-safety-constant /
 * D-36-safety-ux).
 *
 * `SAFETY_CONSTRAINT` is the ONE place the verbatim string lives on the web
 * side: the prebuilt dataset seeds it as every starter's first constraint,
 * `ensureSafetyConstraint` re-injects it before submit, and the editor pins it
 * as a non-removable chip. A drift-guard test reads the core `.py` constant and
 * asserts this literal matches it byte-for-byte, so the two languages cannot
 * diverge silently.
 *
 * The server (`persona_service._guard_safety`) is the authoritative backstop;
 * this client copy is UX + inline feedback, not the enforcement floor.
 */

import type { PersonaDoc } from "@/lib/persona-draft";

export const SAFETY_CONSTRAINT =
  "Do not fabricate information; say when you don't know." as const;

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

/**
 * Return a persona doc guaranteed to carry the verbatim safety constraint as the
 * first `identity.constraints` entry.
 *
 * Idempotent: when the constraint is already present the SAME doc is returned
 * unchanged; otherwise it is prepended. Mirrors the server's
 * `ensure_safety_constraint`, run client-side at assembly for instant feedback,
 * but the server remains the authoritative floor: a request can never strip the
 * constraint past it.
 */
export function ensureSafetyConstraint(doc: PersonaDoc): PersonaDoc {
  const identity = asRecord(doc.identity);
  const constraints = Array.isArray(identity.constraints)
    ? identity.constraints.filter((c): c is string => typeof c === "string")
    : [];
  if (constraints.includes(SAFETY_CONSTRAINT)) return doc;
  return {
    ...doc,
    identity: { ...identity, constraints: [SAFETY_CONSTRAINT, ...constraints] },
  };
}

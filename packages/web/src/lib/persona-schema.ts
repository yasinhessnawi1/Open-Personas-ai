/**
 * Client-side validation of a persona document against the v1.0 schema
 * (Spec 36, D-36-validation).
 *
 * A `zod` mirror of the SOURCE OF TRUTH in
 * `packages/core/src/persona/schema/persona.py`. The server's Pydantic model is
 * authoritative (extra="forbid"); this client schema exists only to catch the
 * common required-field / bounds mistakes BEFORE submit and surface them inline,
 * next to the offending field, instead of relying on a single 422 banner. It is
 * therefore deliberately PERMISSIVE about unknown keys (`.passthrough()`): the
 * editable doc legitimately carries `routing`, `embedding`, `persona_id`, etc.
 * that this layer does not need to police — the server makes the final call.
 *
 * A contract test (persona-schema.test.ts) asserts this mirror stays aligned
 * with persona.py on required fields + enums; if persona.py changes, update both
 * and the test.
 */

import { z } from "zod";
import type { PersonaDoc } from "@/lib/persona-draft";

const selfFactSchema = z
  .object({
    fact: z.string().trim().min(1, "Each self-fact needs text."),
    confidence: z.number().min(0).max(1).optional(),
  })
  .passthrough();

const worldviewSchema = z
  .object({
    claim: z.string().trim().min(1, "Each worldview claim needs text."),
    domain: z.string().optional(),
    epistemic: z.enum(["fact", "belief", "hypothesis", "contested"]).optional(),
    confidence: z.number().min(0).max(1).optional(),
    valid_time: z.string().optional(),
  })
  .passthrough();

const identitySchema = z
  .object({
    name: z.string().trim().min(1, "Name is required."),
    role: z.string().trim().min(1, "Role is required."),
    background: z.string().trim().min(1, "Background is required."),
    language_default: z.string().trim().min(1).optional(),
    constraints: z.array(z.string()).optional(),
    visual_style: z.string().nullish(),
    voice: z.unknown().optional(),
  })
  .passthrough();

/**
 * The validatable shape of a v1.0 persona document. `identity` is required and
 * its required leaves are enforced; everything else mirrors the schema defaults
 * (optional with bounds). Unknown top-level keys pass through.
 */
export const personaDocSchema = z
  .object({
    schema_version: z.literal("1.0", {
      message: 'schema_version must be "1.0".',
    }),
    identity: identitySchema,
    self_facts: z.array(selfFactSchema).optional(),
    worldview: z.array(worldviewSchema).optional(),
    tools: z.array(z.string()).optional(),
    skills: z.array(z.string()).optional(),
  })
  .passthrough();

/** A single field-scoped validation problem, ready to render inline. */
export interface FieldIssue {
  /** Dot/bracket path into the doc, e.g. `identity.name` or `self_facts.2.fact`. */
  path: string;
  /** Human-readable message. */
  message: string;
}

export type ValidationResult =
  | { ok: true }
  | { ok: false; issues: FieldIssue[] };

/**
 * Validate an editable persona doc against the v1.0 mirror.
 *
 * Returns `{ ok: true }` or a list of field-scoped issues (path + message) so
 * the editor can mark the offending inputs. Does NOT mutate the doc and does NOT
 * inject the safety constraint — that is `ensureSafetyConstraint`'s job, run at
 * assembly; validation runs on the already-guarded doc.
 */
export function validatePersonaDoc(doc: PersonaDoc): ValidationResult {
  const result = personaDocSchema.safeParse(doc);
  if (result.success) return { ok: true };
  const issues = result.error.issues.map((issue) => ({
    path: issue.path.join("."),
    message: issue.message,
  }));
  return { ok: false, issues };
}

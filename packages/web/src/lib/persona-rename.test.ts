/**
 * Spec F5 T11 — regression tests for renameInIdentity (D-F5-4 duplicate flow).
 *
 * The hand-rolled flat YAML from the initial T09 implementation was rejected
 * by the API schema (which nests name/role under `identity:`). This helper
 * does a proper js-yaml round-trip on the original persona YAML, mutating
 * only ``identity.name`` and dropping ``persona_id`` so the server generates
 * a fresh row.
 */

// js-yaml v4: load() uses JSON-safe DEFAULT_SCHEMA (no !!python/object
// equivalent; arbitrary-type construction is impossible without explicitly
// passing a custom schema). Test fixtures are repo-local strings.
import yaml from "js-yaml";
import { describe, expect, it } from "vitest";
import { renameInIdentity } from "./persona";

describe("renameInIdentity — D-F5-4 duplicate flow", () => {
  it("mutates identity.name when the YAML has a nested identity block", () => {
    const original = `
schema_version: "1.0"
identity:
  name: Astrid
  role: tenancy law
self_facts: []
`.trim();
    const out = renameInIdentity(original, "Astrid (copy)");
    const parsed = yaml.load(out) as Record<string, unknown>;
    const identity = parsed.identity as Record<string, unknown>;
    expect(identity.name).toBe("Astrid (copy)");
    // Role + other fields preserved.
    expect(identity.role).toBe("tenancy law");
  });

  it("drops persona_id so the server generates a fresh row", () => {
    const original = `
persona_id: original_id
schema_version: "1.0"
identity:
  name: Astrid
  role: x
`.trim();
    const out = renameInIdentity(original, "Astrid (copy)");
    const parsed = yaml.load(out) as Record<string, unknown>;
    expect(parsed.persona_id).toBeUndefined();
  });

  it("falls back to setting top-level name when identity is missing", () => {
    const original = `name: Old\nrole: x\n`;
    const out = renameInIdentity(original, "New");
    const parsed = yaml.load(out) as Record<string, unknown>;
    expect(parsed.name).toBe("New");
  });
});

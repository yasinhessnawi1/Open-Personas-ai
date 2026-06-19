/**
 * Client safety constant + guard (Spec 36, D-36-safety-constant / D-36-safety-ux).
 *
 * Includes the cross-language drift guard: the web literal is read against the
 * Python source of truth so the two can never silently diverge.
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import type { PersonaDoc } from "./persona-draft";
import { ensureSafetyConstraint, SAFETY_CONSTRAINT } from "./persona-safety";

describe("SAFETY_CONSTRAINT", () => {
  it("is the verbatim safety sentence", () => {
    expect(SAFETY_CONSTRAINT).toBe(
      "Do not fabricate information; say when you don't know.",
    );
  });

  it("matches the persona-core Python constant byte-for-byte (drift guard)", () => {
    // Read the SOURCE OF TRUTH directly so a change to either side that is not
    // mirrored fails CI (D-36-safety-constant).
    const pySrc = readFileSync(
      resolve(process.cwd(), "../core/src/persona/schema/safety.py"),
      "utf8",
    );
    const match = pySrc.match(/SAFETY_CONSTRAINT\s*=\s*"([^"]*)"/);
    expect(
      match,
      "could not find SAFETY_CONSTRAINT in safety.py",
    ).not.toBeNull();
    expect(match?.[1]).toBe(SAFETY_CONSTRAINT);
  });
});

describe("ensureSafetyConstraint", () => {
  const docWith = (constraints: unknown): PersonaDoc => ({
    identity: { name: "X", role: "Y", background: "Z", constraints },
  });

  it("prepends the constraint when absent", () => {
    const out = ensureSafetyConstraint(docWith(["Cite a source."]));
    const identity = out.identity as { constraints: string[] };
    expect(identity.constraints).toEqual([SAFETY_CONSTRAINT, "Cite a source."]);
  });

  it("prepends onto an empty / missing constraints list", () => {
    expect(
      (
        ensureSafetyConstraint(docWith([])).identity as {
          constraints: string[];
        }
      ).constraints,
    ).toEqual([SAFETY_CONSTRAINT]);
    expect(
      (
        ensureSafetyConstraint({ identity: {} }).identity as {
          constraints: string[];
        }
      ).constraints,
    ).toEqual([SAFETY_CONSTRAINT]);
  });

  it("is idempotent: returns the same object when already present", () => {
    const doc = docWith([SAFETY_CONSTRAINT, "Cite a source."]);
    expect(ensureSafetyConstraint(doc)).toBe(doc);
  });

  it("does not duplicate or reorder when present but not first", () => {
    const doc = docWith(["Cite a source.", SAFETY_CONSTRAINT]);
    const out = ensureSafetyConstraint(doc);
    expect(out).toBe(doc);
    expect((out.identity as { constraints: string[] }).constraints).toEqual([
      "Cite a source.",
      SAFETY_CONSTRAINT,
    ]);
  });

  it("preserves sibling identity fields and top-level keys", () => {
    const doc: PersonaDoc = {
      schema_version: "1.0",
      identity: { name: "Mara", role: "Operating partner", background: "..." },
      routing: { intelligent: { enabled: true } },
    };
    const out = ensureSafetyConstraint(doc);
    expect(out.schema_version).toBe("1.0");
    expect(out.routing).toEqual({ intelligent: { enabled: true } });
    const identity = out.identity as Record<string, unknown>;
    expect(identity.name).toBe("Mara");
    expect(identity.role).toBe("Operating partner");
  });
});

/**
 * Client persona-doc validation (Spec 36, D-36-validation).
 *
 * Covers the required-field / bounds / enum rules and the passthrough of
 * unknown keys, plus the contract that every shipped starter validates.
 */
import { describe, expect, it } from "vitest";
import type { PersonaDoc } from "./persona-draft";
import { PERSONA_EXAMPLE_CATEGORIES } from "./persona-examples";
import { validatePersonaDoc } from "./persona-schema";

const ALL_EXAMPLES = PERSONA_EXAMPLE_CATEGORIES.flatMap((c) => c.examples);

const validDoc = (): PersonaDoc => ({
  schema_version: "1.0",
  identity: {
    name: "Mara",
    role: "Operating partner",
    background: "Pressure-tests the plan.",
    language_default: "en",
    constraints: ["Do not fabricate information; say when you don't know."],
  },
  self_facts: [{ fact: "Runs the numbers.", confidence: 0.9 }],
  worldview: [
    {
      claim: "Distribution kills startups.",
      domain: "biz",
      epistemic: "belief",
      confidence: 0.8,
    },
  ],
  tools: ["web_search"],
  skills: ["web_research"],
  routing: { intelligent: { enabled: true } },
});

function paths(doc: PersonaDoc): string[] {
  const r = validatePersonaDoc(doc);
  return r.ok ? [] : r.issues.map((i) => i.path);
}

describe("validatePersonaDoc", () => {
  it("accepts a well-formed doc", () => {
    expect(validatePersonaDoc(validDoc())).toEqual({ ok: true });
  });

  it("flags a missing identity.name with a field-scoped path", () => {
    const doc = validDoc();
    (doc.identity as Record<string, unknown>).name = "";
    expect(paths(doc)).toContain("identity.name");
  });

  it("flags a missing required background (the schema requires it)", () => {
    const doc = validDoc();
    delete (doc.identity as Record<string, unknown>).background;
    expect(paths(doc)).toContain("identity.background");
  });

  it("flags an out-of-range self-fact confidence at its index path", () => {
    const doc = validDoc();
    doc.self_facts = [{ fact: "x", confidence: 1.5 }];
    expect(paths(doc)).toContain("self_facts.0.confidence");
  });

  it("flags an empty worldview claim and a bad epistemic value", () => {
    const doc = validDoc();
    doc.worldview = [
      { claim: "", domain: "", epistemic: "vibes", confidence: 0.5 },
    ];
    const p = paths(doc);
    expect(p).toContain("worldview.0.claim");
    expect(p).toContain("worldview.0.epistemic");
  });

  it("rejects a wrong schema_version", () => {
    const doc = validDoc();
    doc.schema_version = "2.0";
    expect(paths(doc)).toContain("schema_version");
  });

  it("passes through unknown keys it does not police (routing, persona_id)", () => {
    const doc = validDoc();
    doc.persona_id = "persona_abc";
    doc.routing = {
      tier_for_generation: "auto",
      intelligent: { enabled: true },
    };
    expect(validatePersonaDoc(doc)).toEqual({ ok: true });
  });

  it("validates EVERY shipped starter structure (T1<->T2 contract)", () => {
    for (const ex of ALL_EXAMPLES) {
      expect(
        validatePersonaDoc(ex.structure as unknown as PersonaDoc),
        ex.id,
      ).toEqual({
        ok: true,
      });
    }
  });
});

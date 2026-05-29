import { describe, expect, it } from "vitest";
import {
  docToYaml,
  type PersonaDoc,
  readIdentity,
  readSelfFacts,
  readWorldview,
  writeIdentityField,
  writeSelfFacts,
  writeStringList,
  writeWorldview,
  yamlToDoc,
} from "./persona-draft";

const SAMPLE = `schema_version: "1.0"
identity:
  name: Astrid
  role: Tenancy assistant
  background: Helps tenants.
  language_default: en
  constraints:
    - Never give binding advice.
self_facts:
  - fact: Specialised in tenancy.
    confidence: 1
worldview:
  - claim: Tenants have rights.
    domain: tenancy
    epistemic: fact
    confidence: 0.95
    valid_time: always
tools:
  - web_search
skills: []
routing:
  tier_for_generation: auto
embedding:
  model: bge-small-en-v1.5
`;

describe("persona-draft round-trip", () => {
  it("parses YAML and reads structured fields", () => {
    const doc = yamlToDoc(SAMPLE);
    const id = readIdentity(doc);
    expect(id.name).toBe("Astrid");
    expect(id.constraints).toEqual(["Never give binding advice."]);
    expect(readSelfFacts(doc)[0]).toEqual({
      fact: "Specialised in tenancy.",
      confidence: 1,
    });
    expect(readWorldview(doc)[0].epistemic).toBe("fact");
  });

  it("survives a doc → yaml → doc round-trip", () => {
    const doc = yamlToDoc(SAMPLE);
    const round = yamlToDoc(docToYaml(doc));
    expect(round).toEqual(doc);
  });

  it("throws on invalid YAML and on a non-mapping top level", () => {
    expect(() => yamlToDoc("identity: : :")).toThrow();
    expect(() => yamlToDoc("- just\n- a\n- list")).toThrow();
  });
});

describe("persona-draft writers preserve sibling keys", () => {
  it("writeIdentityField keeps routing/embedding and other identity fields", () => {
    const doc = yamlToDoc(SAMPLE);
    const next = writeIdentityField(doc, "name", "Bjorn");
    expect(readIdentity(next).name).toBe("Bjorn");
    expect(readIdentity(next).role).toBe("Tenancy assistant"); // sibling kept
    expect((next as PersonaDoc).routing).toEqual(doc.routing); // top-level kept
    expect((next as PersonaDoc).embedding).toEqual(doc.embedding);
  });

  it("writeSelfFacts / writeWorldview / writeStringList replace only their slice", () => {
    const doc = yamlToDoc(SAMPLE);
    const a = writeSelfFacts(doc, [{ fact: "New fact.", confidence: 0.5 }]);
    expect(readSelfFacts(a)).toHaveLength(1);
    expect(readSelfFacts(a)[0].fact).toBe("New fact.");
    expect(a.routing).toEqual(doc.routing);

    const b = writeWorldview(doc, []);
    expect(readWorldview(b)).toEqual([]);

    const c = writeStringList(doc, "tools", ["web_search", "web_fetch"]);
    expect(c.tools).toEqual(["web_search", "web_fetch"]);
    expect(c.skills).toEqual([]);
  });

  it("invalid YAML in the editor leaves the prior doc usable (sync invariant)", () => {
    // Mirrors the editor's behaviour: a parse failure must not lose the form.
    const lastValid = yamlToDoc(SAMPLE);
    let doc = lastValid;
    try {
      doc = yamlToDoc("identity: : :");
    } catch {
      // keep last valid
    }
    expect(doc).toBe(lastValid);
  });
});

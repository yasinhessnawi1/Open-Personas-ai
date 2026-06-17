/**
 * Integrity of the curated starter-persona dataset.
 *
 * The gallery seeds the existing author flow from this data, so the shape and
 * uniqueness guarantees matter: ids must be unique (React keys + selection
 * signal), every example must carry a usable seed, and the flat lookup must
 * cover every example.
 */
import { describe, expect, it } from "vitest";
import {
  ACCENT_OKLCH,
  PERSONA_EXAMPLE_CATEGORIES,
  PERSONA_EXAMPLES_BY_ID,
} from "./persona-examples";

const ALL_EXAMPLES = PERSONA_EXAMPLE_CATEGORIES.flatMap((c) => c.examples);

describe("persona-examples dataset", () => {
  it("has six categories, each with four examples (24 total)", () => {
    expect(PERSONA_EXAMPLE_CATEGORIES).toHaveLength(6);
    for (const category of PERSONA_EXAMPLE_CATEGORIES) {
      expect(category.examples).toHaveLength(4);
    }
    expect(ALL_EXAMPLES).toHaveLength(24);
  });

  it("uses unique ids across all examples and categories", () => {
    const exampleIds = ALL_EXAMPLES.map((e) => e.id);
    expect(new Set(exampleIds).size).toBe(exampleIds.length);

    const categoryIds = PERSONA_EXAMPLE_CATEGORIES.map((c) => c.id);
    expect(new Set(categoryIds).size).toBe(categoryIds.length);
  });

  it("gives every example a name, role, hook, and a substantial seed", () => {
    for (const example of ALL_EXAMPLES) {
      expect(example.name.trim().length).toBeGreaterThan(0);
      expect(example.role.trim().length).toBeGreaterThan(0);
      expect(example.hook.trim().length).toBeGreaterThan(0);
      // Seeds prime the drafter; a one-word seed would be useless.
      expect(example.seed.trim().length).toBeGreaterThan(40);
    }
  });

  it("binds each category to a known accent hue", () => {
    for (const category of PERSONA_EXAMPLE_CATEGORIES) {
      expect(ACCENT_OKLCH[category.accent]).toBeDefined();
    }
  });

  it("exposes a flat lookup covering every example", () => {
    expect(Object.keys(PERSONA_EXAMPLES_BY_ID)).toHaveLength(
      ALL_EXAMPLES.length,
    );
    for (const example of ALL_EXAMPLES) {
      expect(PERSONA_EXAMPLES_BY_ID[example.id]).toEqual(example);
    }
  });

  it("contains no em-dash or en-dash in any visible string", () => {
    // House design rule: hyphen only, never — or –.
    for (const example of ALL_EXAMPLES) {
      const visible = `${example.name} ${example.role} ${example.hook} ${example.seed}`;
      expect(visible).not.toMatch(/[—–]/);
    }
  });

  it("only references MCP servers that exist in the core catalog", () => {
    // Seeds may name an MCP server inline as `mcp:<name>`; every such name must
    // map to a real server in packages/core's BUILTIN_MCP_CATALOG. Keeps the
    // showcase honest — no invented capabilities. (catalog.toml, Spec 27.)
    const KNOWN_MCP_SERVERS = new Set([
      "time",
      "calculator",
      "filesystem",
      "weather",
      "fetch",
      "github",
    ]);
    for (const example of ALL_EXAMPLES) {
      for (const match of example.seed.matchAll(/\bmcp:([a-z_]+)\b/g)) {
        expect(KNOWN_MCP_SERVERS).toContain(match[1]);
      }
    }
  });

  it("collectively exercises a broad spread of real platform capabilities", () => {
    // The starter set should showcase what the platform can actually do, not
    // read as generic chatbots. Each phrase below maps to a shipped capability
    // (tool / skill / MCP / voice / typed memory) verified against the core
    // catalogs; assert the corpus touches every capability family at least once.
    const corpus = ALL_EXAMPLES.map((e) => e.seed.toLowerCase()).join("\n");
    const capabilityFamilies: Record<string, RegExp> = {
      webResearch: /\bresearch|searches?\b|\bweb\b/,
      codeExecution: /code sandbox|run(s)? (in a code|it in)|\bcode\b/,
      codeReview: /review(s|ed)?/,
      documentGeneration: /download(able)?|workbook|document|planner|\bbrief\b/,
      dataAnalysis: /analys(e|es)|\bchart\b|upload(s|ed)?/,
      diagram: /\bdiagram\b/,
      imageGeneration: /\bimage\b|moodboard|concept art/,
      currency: /currenc(y|ies)/,
      voice: /\bvoice\b|out loud/,
      mcp: /\bmcp:/,
      typedMemory: /remember(s|ed)?/,
    };
    for (const [family, pattern] of Object.entries(capabilityFamilies)) {
      expect(corpus, `no example exercises capability: ${family}`).toMatch(
        pattern,
      );
    }
  });
});

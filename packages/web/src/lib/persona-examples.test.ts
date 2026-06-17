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
});

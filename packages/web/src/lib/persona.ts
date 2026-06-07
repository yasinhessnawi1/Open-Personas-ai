import yaml from "js-yaml";

// The PersonaDetail API response carries only the raw `yaml` string (no parsed
// identity), so the detail view parses it here. The v1.0 schema is validated
// server-side; we still read defensively (unknown shapes → safe fallbacks).

export interface WorldviewClaim {
  claim: string;
  domain?: string;
  epistemic?: string;
  confidence?: number;
}

export interface SelfFact {
  fact: string;
  confidence?: number;
}

export interface ParsedPersona {
  name: string;
  role: string;
  background: string;
  languageDefault: string;
  constraints: string[];
  selfFacts: SelfFact[];
  worldview: WorldviewClaim[];
  tools: string[];
  skills: string[];
}

function asString(v: unknown, fallback = ""): string {
  return typeof v === "string" ? v : fallback;
}

function asStringList(v: unknown): string[] {
  return Array.isArray(v)
    ? v.filter((x): x is string => typeof x === "string")
    : [];
}

function asRecord(v: unknown): Record<string, unknown> {
  return v && typeof v === "object" && !Array.isArray(v)
    ? (v as Record<string, unknown>)
    : {};
}

/** Parse a v1.0 persona YAML into a display-friendly shape (defensive). */
export function parsePersonaYaml(src: string): ParsedPersona {
  let doc: Record<string, unknown> = {};
  try {
    // js-yaml v4 `load` is safe by default (no `safeLoad` in v4; the default
    // schema rejects executable/custom tags — unlike PyYAML's `load`).
    doc = asRecord(yaml.load(src));
  } catch {
    // Invalid YAML shouldn't crash the page; fall through to empty defaults.
  }
  const identity = asRecord(doc.identity);
  const selfFacts = Array.isArray(doc.self_facts) ? doc.self_facts : [];
  const worldview = Array.isArray(doc.worldview) ? doc.worldview : [];

  return {
    name: asString(identity.name, "Untitled persona"),
    role: asString(identity.role),
    background: asString(identity.background),
    languageDefault: asString(identity.language_default, "en"),
    constraints: asStringList(identity.constraints),
    selfFacts: selfFacts.map((f) => {
      const r = asRecord(f);
      return {
        fact: asString(r.fact),
        confidence: typeof r.confidence === "number" ? r.confidence : undefined,
      };
    }),
    worldview: worldview.map((w) => {
      const r = asRecord(w);
      return {
        claim: asString(r.claim),
        domain: asString(r.domain) || undefined,
        epistemic: asString(r.epistemic) || undefined,
        confidence: typeof r.confidence === "number" ? r.confidence : undefined,
      };
    }),
    tools: asStringList(doc.tools),
    skills: asStringList(doc.skills),
  };
}

/** Two-letter initials for an avatar fallback. */
export function personaInitials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean);
  if (parts.length === 0) return "?";
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

/**
 * Replace ``identity.name`` in a persona YAML string with ``newName``.
 *
 * Used by the F5 T11 "Duplicate as template" flow (D-F5-4 + D-F5-X-
 * persona-duplicate-flow) — fetches the original persona's full YAML,
 * mutates the name inside the ``identity:`` block, and POSTs the
 * modified YAML so the server creates a fresh persona row with
 * server-generated ``persona_id`` + fresh memory + no conversations.
 *
 * Uses js-yaml round-trip so quoting/indentation stay valid.
 *
 * **Security note:** js-yaml v4's ``load()`` uses the default JSON-safe
 * schema (the unsafe-loader equivalent of Python's ``yaml.load`` doesn't
 * exist in the js-yaml API). The parsed value is treated as opaque +
 * Record-typed; we only set string properties on it.
 */
export function renameInIdentity(yamlSrc: string, newName: string): string {
  const parsed = yaml.load(yamlSrc);
  if (parsed && typeof parsed === "object") {
    const top = parsed as Record<string, unknown>;
    if (top.identity && typeof top.identity === "object") {
      (top.identity as Record<string, unknown>).name = newName;
    } else {
      // Older fixture shape: no nested identity. Set top-level name as fallback.
      top.name = newName;
    }
    // Drop server-only fields if present (persona_id resets at duplicate).
    delete top.persona_id;
  }
  return yaml.dump(parsed);
}

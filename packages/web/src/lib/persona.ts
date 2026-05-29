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

import type { McpCatalogEntry } from "./persona-form";

/**
 * N3 (MCP-as-apps) Task 3 — the pure app-state model.
 *
 * Derives the single presented state of an app for a persona from already-loaded
 * data: the catalog entry + the persona's `tools` allow-list + the persona's
 * `unavailable_mcp_servers` signal (PersonaDetail). No I/O, no React — a pure
 * function reused by the apps chooser (Task 4) and the persona-detail tombstone
 * (Task 5).
 *
 * The four states (N3-D-9):
 *   - `enabled`     — the app's `mcp:<name>` entry is in the persona's tools list.
 *   - `unavailable` — the app name is in `unavailable_mcp_servers`, which BY
 *                     CONTRACT only ever means enabled-then-removed (a never-
 *                     enabled removed server simply isn't in the catalog at all).
 *   - `needs-setup` — the app DECLARES a credential requirement (`secrets[]` or
 *                     `requiredEnv` non-empty). This is NOT "your credential is
 *                     missing": N3 has no read-back of whether the operator set
 *                     it. It means the app *declares* it needs one.
 *   - `available`   — the floor: no declared creds, not enabled, not unavailable.
 *
 * Precedence (FIXED, N3-D-9): `unavailable > enabled > needs-setup > available`.
 * The states co-occur at the data level (an app can be enabled AND declare a
 * credential AND be removed), so exactly one is presented via this order. A
 * removed-but-enabled app surfaces as `unavailable` (degraded → flagged) rather
 * than `enabled` (healthy); a credential-declaring app that isn't on surfaces as
 * `needs-setup` rather than `available`.
 */
export type AppState = "available" | "needs-setup" | "enabled" | "unavailable";

/** The `mcp:` prefix a persona uses to enable a catalog server in its tools list. */
const MCP_PREFIX = "mcp:";

/**
 * Whether a `tools` entry ENABLES this catalog server (`mcp:<name>`).
 *
 * Mirrors the backend `_is_mcp_server_enablement` contract: a server enablement
 * is `mcp:<name>` with EXACTLY one colon. Deeper-prefixed entries are tool-level
 * (`mcp:docker:<tool>`, `mcp:<server>:<tool>`), not server enablement, so they
 * never count as enabling the app.
 */
export function isAppEnabled(
  appName: string,
  tools: readonly string[],
): boolean {
  const entry = `${MCP_PREFIX}${appName}`;
  return tools.includes(entry);
}

/**
 * Whether the app DECLARES a credential requirement (not "your credential is
 * missing" — N3 has no read-back). True iff it lists any secret or required env.
 */
export function declaresCredential(entry: McpCatalogEntry): boolean {
  return entry.secrets.length > 0 || entry.requiredEnv.length > 0;
}

/**
 * Derive the single presented {@link AppState} for an app on a persona.
 *
 * @param entry The catalog entry (carries the declared credential schema).
 * @param tools The persona's `tools` allow-list (the `mcp:<name>` enablement).
 * @param unavailableMcpServers The persona's `unavailable_mcp_servers` signal —
 *   names enabled-then-removed from the catalog (PersonaDetail). Optional /
 *   empty for surfaces (e.g. the new-persona chooser) that have no persona-
 *   detail signal yet.
 */
export function deriveAppState(
  entry: McpCatalogEntry,
  tools: readonly string[],
  unavailableMcpServers: readonly string[] = [],
): AppState {
  // Precedence: unavailable > enabled > needs-setup > available.
  if (unavailableMcpServers.includes(entry.name)) return "unavailable";
  if (isAppEnabled(entry.name, tools)) return "enabled";
  if (declaresCredential(entry)) return "needs-setup";
  return "available";
}

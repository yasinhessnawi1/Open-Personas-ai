#!/usr/bin/env node
/**
 * Spec 33 (D-33-X-clerk-free-gates) — assert the community edition is Clerk-free.
 *
 * Two checks, both fast + deterministic (no full build needed), so they run on
 * every PR:
 *
 *  1. ISOLATION — no `@clerk/*` import anywhere under `src/` except the auth
 *     façade's cloud variants (`src/auth/*.cloud.*`). Catches a stray Clerk
 *     import re-introduced at a call site (the "scoped no-restricted-imports"
 *     gate, as a script).
 *  2. COMMUNITY MODULE GRAPH — starting from the four community `@/auth*` entry
 *     files, walk the transitive *relative* import graph and assert no file in
 *     it imports `@clerk/*`. This is the resolved module graph a community build
 *     pulls in: if it's Clerk-free, the community bundle is Clerk-free.
 *
 * The heavier end-to-end proof (a real `PERSONA_EDITION=community next build`
 * with `@clerk/*` uninstalled, then a `.next` artifact grep) lives in
 * `scripts/check-clerk-free-bundle.sh` for the CI build job.
 */
import { readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const WEB_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(WEB_ROOT, "src");
const AUTH_DIR = join(SRC, "auth");
const CLERK_RE =
  /(?:from|import)\s+["']@clerk\/[^"']+["']|require\(\s*["']@clerk\//;

/** Recursively list every .ts/.tsx file under a dir. */
function walk(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    if (statSync(p).isDirectory()) out.push(...walk(p));
    else if (/\.tsx?$/.test(p)) out.push(p);
  }
  return out;
}

const isTest = (p) => /\.test\.|\.spec\.|__tests__|__mocks__/.test(p);
const isCloudVariant = (p) => /\/auth\/.*\.cloud\.tsx?$/.test(p);

// ---- Check 1: isolation -----------------------------------------------------
const isolationOffenders = walk(SRC)
  .filter((p) => !isTest(p) && !isCloudVariant(p))
  .filter((p) => CLERK_RE.test(readFileSync(p, "utf8")))
  .map((p) => relative(WEB_ROOT, p));

// ---- Check 2: community module graph ----------------------------------------
const COMMUNITY_ENTRIES = [
  "index.community.ts",
  "server.community.ts",
  "provider.community.tsx",
  "middleware.community.ts",
].map((f) => join(AUTH_DIR, f));

function resolveRelative(fromFile, spec) {
  const base = resolve(dirname(fromFile), spec);
  for (const cand of [
    base,
    `${base}.ts`,
    `${base}.tsx`,
    join(base, "index.ts"),
    join(base, "index.tsx"),
  ]) {
    try {
      if (statSync(cand).isFile()) return cand;
    } catch {
      /* not this candidate */
    }
  }
  return null;
}

const graph = new Set();
const graphOffenders = [];
const queue = [...COMMUNITY_ENTRIES];
while (queue.length) {
  const file = queue.pop();
  if (graph.has(file)) continue;
  graph.add(file);
  const src = readFileSync(file, "utf8");
  if (CLERK_RE.test(src)) graphOffenders.push(relative(WEB_ROOT, file));
  // follow relative imports only (a community file must never reach a cloud one)
  for (const m of src.matchAll(/(?:from|import)\s+["'](\.[^"']+)["']/g)) {
    const target = resolveRelative(file, m[1]);
    if (target) queue.push(target);
  }
}

// ---- Report -----------------------------------------------------------------
let failed = false;
if (isolationOffenders.length) {
  failed = true;
  console.error(
    "❌ @clerk/* imported outside src/auth/*.cloud.* (community must stay Clerk-free):",
  );
  for (const f of isolationOffenders) console.error(`   - ${f}`);
}
if (graphOffenders.length) {
  failed = true;
  console.error("❌ a community @/auth module graph file imports @clerk/*:");
  for (const f of graphOffenders) console.error(`   - ${f}`);
}
if (failed) process.exit(1);
console.log(
  `✅ community is Clerk-free: isolation clean, ${graph.size} community auth-graph files carry no @clerk import`,
);

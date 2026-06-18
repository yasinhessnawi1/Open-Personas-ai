#!/usr/bin/env bash
# Spec 33 (D-33-X-clerk-free-gates) — the strongest Clerk-free proof: build the
# community edition and assert no @clerk bytes reach the output artifact.
#
# This is the heavier CI gate (a full `next build`); the per-PR fast gate is
# `scripts/check-clerk-free.mjs`. Run from the web package root.
set -euo pipefail

cd "$(dirname "$0")/.."

echo "→ building community edition (PERSONA_EDITION=community)…"
PERSONA_EDITION=community NEXT_DISABLE_SOURCEMAPS=1 pnpm exec next build

echo "→ grepping the .next artifact for any @clerk reference…"
# Exclude the build cache (.next/cache) and any sourcemaps; we only care about
# shipped server/client chunks.
if grep -rIl --exclude="*.map" "@clerk\|clerkMiddleware\|ClerkProvider" .next/server .next/static 2>/dev/null; then
  echo "❌ community build artifact contains @clerk references — not Clerk-free"
  exit 1
fi

echo "✅ community build artifact is Clerk-free (no @clerk in .next/server or .next/static)"

#!/usr/bin/env bash
# Regenerate the committed OpenAPI artifacts for the persona-api REST surface.
#
#   packages/web/openapi.json      <- dumped from the FastAPI app factory
#   packages/web/src/lib/api/schema.ts  <- openapi-typescript types
#
# Run after the API's request/response models change (spec 09 §5; D-09-1).
# The committed client is NOT generated at runtime — commit the output.
# NOTE: only the REST surface is covered. The SSE event shapes are hand-mirrored
# in src/lib/sse-types.ts (OpenAPI can't model SSE) — see D-09-1.
set -euo pipefail

WEB_DIR="$(cd "$(dirname "$0")/.." && pwd)"
API_DIR="$WEB_DIR/../api"
OUT_JSON="$WEB_DIR/openapi.json"
OUT_TS="$WEB_DIR/src/lib/api/schema.ts"

echo "→ Dumping /openapi.json from the persona-api app factory…"
( cd "$API_DIR" && uv run python -c \
  "import json; from persona_api.app import create_app; print(json.dumps(create_app().openapi(), indent=2))" \
) > "$OUT_JSON"

echo "→ Generating TypeScript types → ${OUT_TS#"$WEB_DIR"/}"
pnpm exec openapi-typescript "$OUT_JSON" -o "$OUT_TS"

echo "→ Formatting generated output to satisfy Biome…"
( cd "$WEB_DIR" && pnpm exec biome format --write "$OUT_TS" "$OUT_JSON" >/dev/null )

echo "✓ Done. Commit openapi.json + src/lib/api/schema.ts."

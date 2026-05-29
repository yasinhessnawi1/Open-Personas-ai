#!/usr/bin/env bash
# Run the persona-api locally for spec-09 web development.
#   - DB: the `persona-pg` Docker container on :5436 (superuser + persona_app RLS role)
#   - Auth: Clerk RS256, verified against the dashboard PEM + the `persona-api` aud
#   - Model: DeepSeek (cheap) for all tiers, key sourced from the repo-root .env
# No secrets live in this file; the DeepSeek key comes from ../../.env (gitignored).
set -euo pipefail
cd "$(dirname "$0")"

# Developer keys (DeepSeek PERSONA_API_KEY, web-search, etc.) from the repo root.
if [ -f ../../.env ]; then set -a; . ../../.env; set +a; fi

export DATABASE_URL="postgresql+psycopg://persona:persona@localhost:5436/persona"
export APP_DATABASE_URL="postgresql+psycopg://persona_app:persona_app@localhost:5436/persona"

# Clerk JWT verification (D-09-2): RS256 + the dashboard PEM + the template aud.
export PERSONA_API_JWT_ALGORITHMS="RS256"
export PERSONA_API_JWT_AUDIENCE="persona-api"
export PERSONA_API_JWT_PUBLIC_KEY="$(cat .secrets/clerk-jwt-public.pem)"

# Force ALL tiers → DeepSeek (cheap) for spec-09 dev. The repo .env sets per-tier
# providers (frontier=anthropic, small=groq); those take precedence over the
# single PERSONA_PROVIDER fallback, so each tier must be overridden explicitly.
# The DeepSeek key is read from whichever var holds it.
DEEPSEEK_KEY="${PERSONA_DEEPSEEK_API_KEY:-${PERSONA_MID_API_KEY:-${PERSONA_API_KEY:-}}}"
for TIER in FRONTIER MID SMALL; do
  export "PERSONA_${TIER}_PROVIDER=deepseek"
  export "PERSONA_${TIER}_MODEL=deepseek-chat"
  export "PERSONA_${TIER}_API_KEY=${DEEPSEEK_KEY}"
done
export PERSONA_PROVIDER="deepseek"
export PERSONA_MODEL="deepseek-chat"
export PERSONA_API_KEY="${DEEPSEEK_KEY}"

exec uv run uvicorn persona_api.app:create_app --factory --host 127.0.0.1 --port 8000

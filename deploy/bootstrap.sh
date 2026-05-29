#!/usr/bin/env bash
# Open Persona — first-boot database bootstrap (Spec 11, T10).
# Idempotent. Safe to re-run after stack updates / migration bumps.
#
# Order (the launch gap a stale dev-DB surfaced during pre-flight Gate 1):
#   1. Create the non-superuser `persona_app` role (production RLS connects as it).
#   2. Run alembic upgrade head (manual per spec 07 §7 — never auto-on-startup).
#   3. Grant schema + table + sequence privileges to persona_app + set default
#      privileges so future migrations' tables inherit the grants.
#
# Run AFTER `docker compose -f docker-compose.production.yml up -d` and BEFORE
# the API serves real traffic. The Compose `api` healthcheck will report
# unhealthy until step 2 lands the tables.
#
# Usage:
#   ./deploy/bootstrap.sh                       # uses ./.env.production
#   ENV_FILE=/path/to/.env.production ./deploy/bootstrap.sh
set -euo pipefail

cd "$(dirname "$0")"
ENV_FILE="${ENV_FILE:-./.env.production}"

if [ ! -f "$ENV_FILE" ]; then
  echo "ERROR: $ENV_FILE not found. Copy .env.production.example to .env.production first." >&2
  exit 1
fi
set -a; . "$ENV_FILE"; set +a

: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set in $ENV_FILE}"
: "${PERSONA_APP_DB_PASSWORD:?PERSONA_APP_DB_PASSWORD must be set in $ENV_FILE}"

COMPOSE_FILE="${COMPOSE_FILE:-./docker-compose.production.yml}"
PG="docker compose -f $COMPOSE_FILE exec -T postgres psql -U persona -d persona -v ON_ERROR_STOP=1"
API="docker compose -f $COMPOSE_FILE run --rm api"

echo "==> 1/3 Provision the persona_app role (idempotent)"
$PG -v approle_pw="$PERSONA_APP_DB_PASSWORD" <<'SQL'
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'persona_app') THEN
    EXECUTE format('CREATE ROLE persona_app LOGIN PASSWORD %L NOSUPERUSER', :'approle_pw');
  ELSE
    EXECUTE format('ALTER ROLE persona_app WITH PASSWORD %L', :'approle_pw');
  END IF;
END$$;
SQL

echo "==> 2/3 Run alembic upgrade head"
$API uv run alembic -c alembic/alembic.ini upgrade head

echo "==> 3/3 Grant persona_app schema + table + sequence privileges"
$PG <<'SQL'
GRANT USAGE ON SCHEMA public TO persona_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO persona_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO persona_app;
-- Future tables inherit the grants (a new migration won't need a re-bootstrap).
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO persona_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO persona_app;
SQL

echo
echo "Bootstrap complete. The API healthcheck should turn healthy within ~30s."
echo "Verify: curl -fsS http://127.0.0.1:8000/healthz"

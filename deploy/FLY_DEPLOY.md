# Deploying `persona-api` to Fly.io

The Fly.io path — alternative to the Docker Compose VPS path
(`docker-compose.production.yml` + `bootstrap.sh` + `Caddyfile.example`). Fly's
edge terminates TLS automatically, so no Caddy is needed.

## What Fly buys you here

- **TLS for free** — `fly certs add api.openpersona.dev` and you're done.
- **One-Machine deploy** — matches S08-4 / D-08-5 (in-process run bus, in-memory rate limiter).
- **Volume-backed audit logs** — survives Machine restarts.

> **Note on Postgres:** Fly Managed Postgres (`fly mpg`) starts at $38/mo
> for the Basic plan, and the legacy unmanaged `fly pg` is no longer
> officially supported. The launch path uses **Neon** (free tier, pgvector,
> Frankfurt region — matches Fly `fra` for <5 ms DB latency) instead —
> see §1 below. The cost stays at $0 for Postgres, and we sidestep the
> support-status warning on legacy Fly PG.

## Prerequisites

- `flyctl` installed (`brew install flyctl`).
- `fly auth login` (you already have an account per the launch session).
- Repo cloned locally (Fly builds from your local context).

---

## 1. Create the Fly app + volume + Neon Postgres

```bash
APP=open-persona-api
REGION=fra            # Frankfurt — close to Vercel's fra1 (D-11-2)

# 1a. The API app.
flyctl apps create $APP --org personal

# 1b. The audit-log volume (small; the JSONL logs rotate). Free under 3 GB.
flyctl volumes create persona_audit --app $APP --region $REGION --size 1 --yes
```

### 1c. Provision a Neon Postgres project (one-time, 5 minutes)

1. Go to **https://console.neon.tech** and sign up (Google or GitHub; **no card required**).
2. Create a project:
   - Project name: `open-persona`
   - Postgres version: 16
   - **Region: AWS Europe (Frankfurt) — `eu-central-1`** (matches Fly `fra`; <5 ms DB latency).
   - Database name: leave the default `neondb`.
3. On the project page, copy the **direct (unpooled) DSN** — toggle "Pooled connection" *off*.
   - Pooled DSN uses PgBouncer transaction mode, which silently breaks our D-08-1
     structural-RLS pattern (session-level `set_config('app.current_user_id', …, false)` is
     lost between transactions). The direct DSN supports session-level state; SQLAlchemy
     maintains its own pool on top.
4. Paste the DSN into your local `.env` as `DATABASE_URL=postgresql://...`. The repo's
   `.env` is gitignored.

### 1d. Bootstrap the Neon database

Done from your laptop (the API container doesn't need outbound psql tools):

```bash
# Generate a strong password for the non-superuser persona_app role and persist it.
PG_APP_PW=$(python3 -c "import secrets; print(secrets.token_urlsafe(32))")
grep -q "^PERSONA_APP_DB_PASSWORD=" .env || echo "PERSONA_APP_DB_PASSWORD=$PG_APP_PW" >> .env
```

Then run this Python (it parses `.env`, patches the SQLAlchemy dialect, creates
`persona_app`, runs `alembic upgrade head`, and grants the role tables + sequences):

```bash
.venv/bin/python <<'PY'
import os, re
from pathlib import Path
for line in Path('.env').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    k, _, v = line.partition('=')
    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

dsn = os.environ['DATABASE_URL']
if dsn.startswith('postgresql://') and '+psycopg' not in dsn:
    dsn = dsn.replace('postgresql://', 'postgresql+psycopg://', 1)
pw = os.environ['PERSONA_APP_DB_PASSWORD']

from sqlalchemy import create_engine, text
eng = create_engine(dsn, isolation_level='AUTOCOMMIT')
with eng.connect() as c:
    c.execute(text(f"""
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='persona_app') THEN
    EXECUTE format('CREATE ROLE persona_app LOGIN NOSUPERUSER PASSWORD %L', '{pw}');
  END IF;
END$$;
GRANT USAGE ON SCHEMA public TO persona_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO persona_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO persona_app;
"""))

import sys
sys.path[0:0] = ['packages/core/src','packages/runtime/src','packages/api/src']
from alembic import command
from alembic.config import Config
cfg = Config('packages/api/alembic/alembic.ini')
cfg.set_main_option('script_location', 'packages/api/alembic')
cfg.set_main_option('sqlalchemy.url', dsn)
command.upgrade(cfg, 'head')

# Grants on the now-existing tables (idempotent).
with eng.connect() as c:
    c.execute(text('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO persona_app'))
    c.execute(text('GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO persona_app'))
PY
```

### 1e. Switch `DATABASE_URL` from pooled to direct (if you grabbed the pooled DSN)

Neon's direct host is the pooled host with `-pooler` stripped. If your DSN shows
`ep-xxx-pooler.c-N.eu-central-1.aws.neon.tech`, drop the `-pooler`. The
launch-session helper did this automatically; the same script for reuse:

```bash
sed -i.bak 's/-pooler\././' .env && rm .env.bak    # macOS BSD sed; on Linux: -i ''
```

---

## 2. Stage the API secrets on the Fly app

We use `flyctl secrets import` (stdin NAME=VALUE lines — safer than argv-leaking
secrets). The Clerk PEM is multiline so it goes via a separate `flyctl secrets
set` call. Both use `--stage` so nothing tries to redeploy mid-staging.

```bash
# Stage 16 single-line secrets from .env (incl. DATABASE_URL + APP_DATABASE_URL we
# build by swapping persona_app credentials onto the same host/db/params).
.venv/bin/python <<'PY' | flyctl secrets import --app open-persona-api --stage
import os, re
from pathlib import Path
env = {}
for line in Path('.env').read_text().splitlines():
    line = line.strip()
    if not line or line.startswith('#') or '=' not in line: continue
    k, _, v = line.partition('=')
    env[k.strip()] = v.strip().strip('"').strip("'")

dsn = env['DATABASE_URL']
if dsn.startswith('postgresql://') and '+psycopg' not in dsn:
    dsn = dsn.replace('postgresql://', 'postgresql+psycopg://', 1)
m = re.match(r'(.+)://[^:]+:[^@]+@(.+)$', dsn)
app_dsn = f'{m.group(1)}://persona_app:{env["PERSONA_APP_DB_PASSWORD"]}@{m.group(2)}'
deepseek = env['PERSONA_MID_API_KEY']

secrets = {
    'DATABASE_URL': dsn, 'APP_DATABASE_URL': app_dsn,
    'PERSONA_PROVIDER':'deepseek','PERSONA_MODEL':'deepseek-chat','PERSONA_API_KEY':deepseek,
    'PERSONA_FRONTIER_PROVIDER':env['PERSONA_FRONTIER_PROVIDER'],
    'PERSONA_FRONTIER_MODEL':env['PERSONA_FRONTIER_MODEL'],
    'PERSONA_FRONTIER_API_KEY':env['PERSONA_FRONTIER_API_KEY'],
    'PERSONA_MID_PROVIDER':env['PERSONA_MID_PROVIDER'],
    'PERSONA_MID_MODEL':env['PERSONA_MID_MODEL'],
    'PERSONA_MID_API_KEY':env['PERSONA_MID_API_KEY'],
    'PERSONA_SMALL_PROVIDER':'deepseek','PERSONA_SMALL_MODEL':'deepseek-chat','PERSONA_SMALL_API_KEY':deepseek,
    'PERSONA_WEB_SEARCH_PROVIDER':'tavily',
    'PERSONA_WEB_SEARCH_API_KEY':env['PERSONA_WEB_SEARCH_API_KEY'],
}
for k, v in secrets.items(): print(f'{k}={v}')
PY

# Stage the Clerk PEM separately (multiline values can't go through secrets-import).
flyctl secrets set --app open-persona-api --stage \
  PERSONA_API_JWT_PUBLIC_KEY="$(cat packages/api/.secrets/clerk-jwt-public.pem)"

# Sanity:
flyctl secrets list --app open-persona-api
```

> **Note.** The launch-session used Tavily as the search provider (free 1k/mo,
> no card required); D-03-9 originally specified Brave. Both providers work —
> set `PERSONA_WEB_SEARCH_PROVIDER` to whichever key you have.

For reference, the original Brave-style argv set looked like:

```bash
flyctl secrets set --app $APP \
  PERSONA_PROVIDER=deepseek \
  PERSONA_MODEL=deepseek-chat \
  PERSONA_API_KEY=$DEEPSEEK_KEY \
  PERSONA_FRONTIER_PROVIDER=anthropic \
  PERSONA_FRONTIER_MODEL=claude-sonnet-4-6 \
  PERSONA_FRONTIER_API_KEY=$ANTHROPIC_KEY \
  PERSONA_MID_PROVIDER=deepseek \
  PERSONA_MID_MODEL=deepseek-chat \
  PERSONA_MID_API_KEY=$DEEPSEEK_KEY \
  PERSONA_SMALL_PROVIDER=deepseek \
  PERSONA_SMALL_MODEL=deepseek-chat \
  PERSONA_SMALL_API_KEY=$DEEPSEEK_KEY \
  PERSONA_WEB_SEARCH_PROVIDER=tavily \
  PERSONA_WEB_SEARCH_API_KEY=$SEARCH_KEY \
  PERSONA_API_JWT_PUBLIC_KEY="$(cat packages/api/.secrets/clerk-jwt-public.pem)"
  # CORS — set this LATER (§5) once Vercel gives you the persona-web URL.
```

`PERSONA_API_JWT_AUDIENCE`, `PERSONA_API_JWT_ALGORITHMS`, `PERSONA_LOG_LEVEL`,
`PERSONA_AUDIT_ROOT`, `PERSONA_TURNLOG_PATH` are already set in `fly.toml`
under `[env]` — no action needed.

---

## 3. Deploy

```bash
# From the repo root (the Dockerfile's COPY paths assume that as context).
# --remote-only does the build on Fly's builders — saves local disk + bandwidth.
flyctl deploy -c deploy/fly.toml --app open-persona-api --remote-only
```

First build is ~3–5 minutes (uv sync of the whole workspace + sentence-transformers).
Subsequent builds use Docker layer caching and are much faster.

The Machine should report healthy on first start because §1d already ran the
schema migration + grants against Neon. Verify:

```bash
flyctl status --app open-persona-api
curl -fsS https://open-persona-api.fly.dev/healthz   # {"status":"ok","db":"connected"}
```

---

## 4. (Schema + persona_app are already done in §1d)

The legacy "fly pg connect + ssh console alembic + grants again" flow that the
Fly-managed-PG path used is collapsed into §1d's single Python script: it
provisions the role, runs alembic, and grants on the now-existing tables in
one transactional batch. Future migration bumps re-run the same script (the
DO-block + alembic upgrade are both idempotent).

---

## 5. Custom domain + TLS (once DNS is in your control)

```bash
# A-record / AAAA-record / CNAME on api.openpersona.dev → $APP.fly.dev
flyctl certs add --app $APP api.openpersona.dev
flyctl certs check --app $APP api.openpersona.dev   # wait for "ready"
```

Then update CORS:

```bash
# Replace with the real Vercel URL from #11.
flyctl secrets set --app $APP \
  PERSONA_API_CORS_ORIGINS="https://persona.openpersona.dev,https://<your-vercel-app>.vercel.app"
```

---

## 6. Smoke test

```bash
# Unauth — 401 with structured body.
curl -fsS -i https://api.openpersona.dev/healthz
curl -i  https://api.openpersona.dev/v1/personas -H "Authorization: Bearer fake"
# expect: HTTP/2 401 + {"error":"authentication_error", ...}
```

If `/healthz` returns 200 and `/v1/personas` returns 401 with the structured
error envelope, the deploy is green. Move on to **#11 — Vercel** in
LAUNCH_CHECKLIST.md.

---

## Future migrations

After any `alembic` revision bump, repeat **4b** (and only 4b — the
`persona_app` role already exists, and the `ALTER DEFAULT PRIVILEGES` from 4a
makes new tables inherit grants automatically):

```bash
flyctl ssh console --app $APP \
  -C "sh -c 'cd /app/packages/api && uv run alembic -c alembic/alembic.ini upgrade head'"
```

## Troubleshooting

- **`relation "personas" does not exist`** — you forgot step 4b. Run it.
- **`permission denied for schema public`** — you forgot step 4a or 4c. Run both.
- **CORS preflight 403 from the web app** — `PERSONA_API_CORS_ORIGINS` isn't set, or the Vercel preview URL changed. Re-set the secret with the exact origin (no trailing slash).
- **First request after deploy stalls 10+ s** — bge-small loads weights on first encode (D-02-10 lazy pattern). Subsequent requests are fast. The healthcheck `grace_period = 30s` covers it.
- **OOM on soak / agentic runs** — bump `memory = "2048mb"` in `fly.toml` and redeploy.

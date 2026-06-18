# persona-api

> The hosted FastAPI service for Open Persona — REST + SSE over the typed-memory runtime.

`persona-api` is **layer 2** of the [Open Persona](../../README.md) stack: the
HTTP composition root that exposes [`persona-core`](../core/README.md) and
[`persona-runtime`](../runtime/README.md) over a REST + Server-Sent-Events
surface. It owns transport, persistence, auth, and the per-edition commercial
seams; it sits between [`persona-web`](../web/README.md) (the browser client)
and the in-process runtime.

---

## What it is / where it fits

The API is the only network-facing process in the text stack. It owns
everything the runtime explicitly does not: HTTP transport, persistence,
request ownership, credits, the agentic-run event bus, the code-execution
sandbox pool, and produced-file storage. The runtime is composed *inside* the
API (`services/runtime_factory.py`); each request is conditioned on the
caller's persona and typed memory before it ever reaches a model.

It ships in **two editions**, selected by a single `PERSONA_EDITION` switch:

- **community** (default) — local, single-user, **zero-infra**. SQLite + a
  local Chroma directory, **no auth wall, no credits, no Postgres, no Docker**.
  A fixed local owner is seeded at boot; the whole product runs from one model
  API key.
- **cloud** — the owner's commercial hosting: Clerk JWT auth, multi-tenant
  Postgres + pgvector with Row-Level Security, and metered credits.

The edition is a *seam, not scattered flags*: `OwnerResolver` (who owns this
request), `CreditsPolicy` (is it metered), and the relational/vector backend
are chosen once at the app factory. Every call site downstream consumes the
selected interface, so `owner_id`, RLS scoping, and ownership pre-flights are
identical across editions — community just feeds them a constant.

## Features

- **Persona CRUD** with full YAML round-trip; auto-generates a
  demographic-safe avatar on create (free, fail-soft) and auto-picks a fitting
  voice.
- **Streaming chat** — SSE-streamed conversations with visible identity,
  tool-call events, per-turn tier badges, and file/image attachments.
- **Agentic runs** — create / SSE-stream / cancel / ask-user reply over an
  in-process event bus (catch-up + reconcile-on-drop).
- **Documents & uploads** — ingestion of txt / md / code / csv / docx / xlsx /
  pdf plus image upload for vision (Pillow downscale + EXIF strip).
- **Image generation** — pre-deduct credits + per-user advisory-lock cap;
  artifacts served back through the API.
- **Tools & MCP** — toolbox introspection; bring-your-own MCP servers with
  encrypted-at-rest credentials (Fernet); code execution via the E2B Code
  Interpreter sandbox (lazy-imported; absent without a key).
- **Credits & usage** — balance + per-turn usage (`/me`), pre-deduct + refund
  (cloud); unlimited no-op (community).
- **Safety guard** — a community/no-auth process refuses to start on a
  non-loopback bind unless `PERSONA_ALLOW_PUBLIC_NOAUTH=1` is set, so an open,
  unauthenticated instance can't accidentally burn the operator's model keys.

Single uvicorn worker by design — the in-process run event bus and in-memory
rate limiter assume one worker.

## Install / run

`persona-api` is a `uv` workspace package. From the repo root:

```bash
uv sync                       # install the workspace
```

### Community (default — zero infra)

```bash
# one model API key is all community needs
export PERSONA_PROVIDER=anthropic
export PERSONA_API_KEY=sk-ant-...
export PERSONA_MODEL=claude-sonnet-4-6

# SQLite + Chroma are created on first boot; a fixed local owner is seeded.
# PERSONA_EDITION defaults to community.
uv run uvicorn persona_api.app:create_app --factory --port 8000
```

### Cloud (Clerk auth + Postgres RLS + credits)

```bash
docker compose up -d postgres                 # Postgres 16 + pgvector
export PERSONA_EDITION=cloud
# + DATABASE_URL / APP_DATABASE_URL, Clerk JWT vars, provider keys

uv run alembic -c packages/api/alembic.ini upgrade head    # migrations are explicit
cd packages/api && bash run-local.sh          # api :8000 (+ voice :8001)
```

Migrations never run on container start. Production runs from the included
`Dockerfile`:

```bash
docker build -t persona-api -f packages/api/Dockerfile .
docker run -p 8000:8000 --env-file .env persona-api    # sets PERSONA_EDITION=cloud
```

### Test

```bash
uv run pytest packages/api                 # unit (default)
uv run pytest packages/api -m integration  # needs Postgres
uv run pytest packages/api -m external     # needs live provider keys
uv run mypy packages/api/src
uv run ruff check packages/api
```

## Usage / key surfaces

All routes are under `/v1`:

| Group | What |
| --- | --- |
| `personas` | list / create / read / update / delete; YAML round-trip; avatar + voice auto-pick on create |
| `conversations` | chat resource + **SSE streaming** + cascade delete |
| `runs` | agentic-run create / **SSE stream** / cancel / ask-user reply |
| `documents`, `uploads` | document ingestion + image upload (vision) |
| `imagegen`, `artifacts` | image generation (credit-gated) + chart/image serve |
| `tools`, `mcp_servers` | toolbox introspection; bring-your-own MCP servers |
| `me` | credit balance + per-turn usage |
| `health` | liveness + readiness |

**SSE.** Chat and runs stream over Server-Sent Events (token deltas, tool-call
events, run-timeline events) — OpenAPI cannot model SSE, so the event shapes
are the contract consumed by the web client.

**Auth (cloud).** Clerk JWT (RS256), verified via the `JwtVerifier` seam in
`persona-core`. Row-Level Security at the database layer (`persona_app`
non-superuser role; per-request `owner_id` bound through the RLS engine
context). **Community** has no auth: a fixed local owner, no JWT required, RLS
fed a constant.

## Architecture (brief)

```
persona-web  ──HTTP / SSE / OpenAPI──▶  persona-api  ──in-process──▶  persona-runtime ──▶ persona-core
                                          │
                          edition seam: OwnerResolver · CreditsPolicy · backend
                          community → SQLite + Chroma (no auth/credits)
                          cloud     → Postgres + pgvector + RLS + Clerk + credits
```

The API depends on `persona-core` (typed memory, schema, backends) and
`persona-runtime` (the turn loop, router, prompt builder), both `uv` workspace
packages. It never reaches into a provider SDK directly — that boundary lives
in `persona-core`.

## License

`persona-api` is licensed under **PolyForm Noncommercial 1.0.0** — see
[LICENSE](LICENSE). It is **source-available, not OSI "open source"**: you may
read, modify, and self-host it for personal, research, evaluation, educational,
and other **noncommercial** use, but **commercial use requires a separate
license** from the rights holder. The engine it composes
(`persona-core` / `persona-runtime` / `persona-voice`) is separately
**MIT**-licensed and free for any use.

## Links

- [Open Persona root README](../../README.md)
- [`persona-core`](../core/README.md) · [`persona-runtime`](../runtime/README.md) · [`persona-voice`](../voice/README.md) · [`persona-web`](../web/README.md)
- [CHANGELOG](CHANGELOG.md)

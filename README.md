# Open Persona: Typed-memory AI persona platform with tier-routed model selection

Open Persona is a platform for building and running AI personas that maintain a
stable identity across long, multi-turn, tool-using conversations, including
real-time voice. The thing that makes it different from "ChatGPT with a system
prompt" is the **typed memory + tier-routed runtime**: a persona's identity,
self-facts, worldview, and episodic memory are structured, versioned, typed
stores (not free-text), and the runtime puts a right-sized model on each task.
Frontier models go where persona quality matters; smaller and cheaper models
go everywhere else. A voice trunk (LiveKit + streaming STT + streaming TTS)
layers sub-second-latency real-time conversation onto the same persona surface.

---

## Architecture

```
   ┌─────────────────────────────────────────────────────────────────────┐
   │                         Web App (Next.js)                           │
   │    auth · persona authoring · chat UI · voice client (in dev)       │
   └──────────────────────────────┬──────────────────────────────────────┘
                                  │ HTTPS / SSE / OpenAPI
   ┌──────────────────────────────▼──────────────────────────────────────┐
   │                    Hosted API (FastAPI)                             │
   │  · users · personas · conversations · credits · audit log           │
   │  · /v1/personas/:id/chat   (SSE streaming)                          │       ┌──────────────────────────┐
   │  · /v1/personas/:id/run    (agentic task)                           │◀────▶ │   persona-voice trunk    │
   │  · /v1/personas/author     (LLM-assisted authoring)                 │       │  LiveKit substrate (V1)  │
   └──────────────────────────────┬──────────────────────────────────────┘       │  Streaming STT     (V2)  │
                                  │ in-process                                   │  Streaming TTS     (V3)  │
   ┌──────────────────────────────▼──────────────────────────────────────┐       │  Turn-taking       (V4)  │
   │              persona-runtime (Python)                               │       │  Reply producer    (V5)  │
   │  ┌────────────┐  ┌──────────┐  ┌─────────┐  ┌──────────────────┐    │       │  Frontend voice    (V6)  │
   │  │ Memory     │  │  Router  │  │ Toolbox │  │ History manager  │    │       └──────────────────────────┘
   │  │  identity  │  │ frontier │  │  web    │  │ summarise+compact│    │
   │  │  self      │  │ mid      │  │  fs     │  │ skill budgeter   │    │
   │  │  world     │  │ small    │  │  mcp    │  │                  │    │
   │  │  episodic  │  │          │  │  skills │  │                  │    │
   │  └────────────┘  └──────────┘  └─────────┘  └──────────────────┘    │
   │                AgenticLoop (plan → act → reflect)                   │
   └──────────────────────────────┬──────────────────────────────────────┘
                                  │
   ┌──────────────────────────────▼──────────────────────────────────────┐
   │              persona-core (Python library, MIT licensed)            │
   │  · YAML schema · validation · registry                              │
   │  · four typed memory stores (Chroma + Postgres/pgvector)            │
   │  · model backend abstraction (frontier APIs + local HF + Ollama)    │
   │  · image-gen, sandbox, audit, logging, CLI                          │
   └─────────────────────────────────────────────────────────────────────┘
                │                                  │
                ▼                                  ▼
       ┌────────────────┐                ┌──────────────────────────────┐
       │  Postgres      │                │   Model providers            │
       │  + pgvector    │                │   Anthropic · OpenAI ·       │
       │  + object      │                │   DeepSeek · Groq · Together │
       │   storage      │                │   NVIDIA · OpenRouter ·      │
       │                │                │   Ollama · local HF          │
       └────────────────┘                └──────────────────────────────┘
```

Four layers, each only talking to the one below it. The voice trunk attaches
to the API layer and reuses the same persona / memory / runtime surface for
its reply producer. Voice is not a parallel stack; it's the same stack with
audio I/O wrapped around the turn loop.

---

## Status

### Shipped (v0.1, June 2026)

- `persona-core`: typed memory stores (identity / self_facts / worldview /
  episodic), versioned append-only updates with `history`/`rollback`, YAML
  schema + validator, eight model-provider backends, image generation,
  sandboxed code execution, CLI (`persona init / chat / run / serve`), audit
  log.
- `persona-runtime`: conversation loop, prompt builder with skill-token
  budgeting, summarise-and-compact history manager, tier router (frontier /
  mid / small) with multi-model-per-tier cross-provider fallback, agentic
  plan-act-reflect loop, tool dispatch.
- `persona-api`: FastAPI service with auth, persona CRUD, conversations,
  credits, audit log, SSE-streaming `/chat`, agentic `/run`, and LLM-assisted
  `/author`.
- `persona-web`: Next.js app with persona authoring, chat UI, and a billing
  dashboard stub.
- `persona-voice V1`: LiveKit substrate (rooms, agent worker, four-seam
  pipeline scaffold).
- `persona-voice V2`: Deepgram streaming STT.
- `persona-voice V3`: Cartesia Sonic streaming TTS plus per-persona voice as a
  first-class identity attribute.
- `persona-voice V4`: turn-taking + barge-in — the conversational state machine,
  automatic endpointing, fast-and-discriminating interruption, and full-loop
  latency ownership (the orchestration core; pure-Python on the V1/V2/V3 seams).
- `persona-voice V5`: persona/runtime/memory integration — fills V4's reply-producer
  seam with the real persona-conditioned, tier-routed, streaming, cancellable
  generation and writes voice turns to the same episodic store as text (unified
  memory). The voice persona *is* the persona (shared prompt-building + retrieval,
  never a bypass), with a voice latency-routing gate, off-critical-path compaction,
  conversational voice tools, and barge-over-honest memory.

### In development

- `persona-voice V6`: frontend voice client.

The four-layer text platform (`core` + `runtime` + `api` + `web`) is at v0.1
and usable end-to-end. The voice trunk is live through V5 (transport, STT, TTS,
turn-taking, and persona-conditioned generation + unified memory); real-time
two-way conversation completes when V6 (the frontend voice client) lands.

---

## Quick start

### Run the whole product locally — community edition (zero infra)

The default edition (`PERSONA_EDITION=community`) is a **clone-and-run** local
self-host: **no auth, no credits, no Postgres, no Docker**. Persistence is a
SQLite file + a local Chroma directory. You only need Python 3.11+,
[uv](https://docs.astral.sh/uv/), [pnpm](https://pnpm.io/), and a model API key.

```bash
# 1. clone + install
git clone https://github.com/yasinhessnawi1/Open-Persona.git
cd open-persona
uv sync

# 2. set ONE model API key (community needs nothing else)
export PERSONA_PROVIDER=anthropic
export PERSONA_API_KEY=sk-ant-...
export PERSONA_MODEL=claude-sonnet-4-6

# 3. run the API (SQLite + Chroma created on first boot; a fixed local owner is
#    seeded; no sign-in wall). PERSONA_EDITION defaults to community.
uv run uvicorn persona_api.app:create_app --factory --port 8000

# 4. run the web app (community build is Clerk-free)
cd packages/web && pnpm install && pnpm dev
```

For **noncommercial** use under clear per-package licenses (MIT engine,
source-available app — see [License](#license)).

### Cloud edition (the owner's commercial hosting)

`PERSONA_EDITION=cloud` reproduces the hosted behavior — Clerk auth, multi-tenant
Postgres RLS, metered credits. It needs `DATABASE_URL` / `APP_DATABASE_URL`, the
JWT/Clerk vars, and `docker compose up -d postgres`. Both the API process and the
web build must set `PERSONA_EDITION=cloud`.

### Developing / testing

```bash
docker compose up -d postgres          # for the hosted-path integration tests
uv run pytest                          # default suite (integration + external skip)
uv run pytest -m integration           # integration suite (needs Postgres)
uv run mypy packages/core/src --strict # type-check
uv run ruff check                      # lint
uv run lint-imports                    # the MIT-engine ↛ PolyForm-app license boundary
cd packages/web && pnpm check:clerk-free   # community bundle is Clerk-free
```

Per-package quickstarts (install one package standalone, run the CLI, embed
the library in your own code) live in each package's own README. See the
table below.

For environment variables (provider keys, Postgres URLs, voice provider
credentials, feature toggles), copy `.env.example` to `.env` and fill in
what you need. Each section in `.env.example` is grouped by package and
documents the minimum set needed for that package to run.

---

## Packages

| Package | Description | License | Status |
| --- | --- | --- | --- |
| [`packages/core/`](packages/core/README.md) | Typed memory stores, persona schema, model backends, image-gen, sandbox, CLI. The library you `pip install persona-core` to get. | **MIT** | Shipped (v0.1) |
| [`packages/runtime/`](packages/runtime/README.md) | Conversation loop, tier router, prompt builder, history manager, agentic loop, tool dispatch. | **MIT** | Shipped (v0.1) |
| [`packages/voice/`](packages/voice/README.md) | LiveKit-based voice trunk: streaming STT, streaming TTS, turn-taking, real-time persona conversation. | **MIT** | V1-V3 shipped, V4-V6 in development |
| [`packages/api/`](packages/api/) | Hosted FastAPI service: auth, persona CRUD, SSE-streaming chat, agentic run, LLM-assisted authoring. | PolyForm-NC 1.0.0 (source-available, noncommercial) | In development |
| [`packages/web/`](packages/web/README.md) | Next.js web app: persona authoring, chat UI, billing dashboard. | PolyForm-NC 1.0.0 (source-available, noncommercial) | In development |

Each package has its own `CHANGELOG.md`, `pyproject.toml`, and version line.
The workspace `pyproject.toml` at the repo root pins them together via uv
workspace.

---

## License

Open Persona is an **open-core** project — a permissively-licensed engine plus a
source-available application. There is no single repo-wide license; each package
declares its own (SPDX expression in its `pyproject.toml` / `package.json`, with
a `LICENSE` file alongside).

**Engine — MIT (true OSI open source):** `packages/core/`, `packages/runtime/`,
`packages/voice/` are licensed under the [MIT License](https://opensource.org/license/mit).
Free for **any** use, including commercial.

**Application — PolyForm Noncommercial 1.0.0 (source-available, NOT OSI open
source):** `packages/api/` and `packages/web/` are licensed under
[PolyForm Noncommercial 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0).
The source is public — you may read, modify, and self-host it for personal,
research, evaluation, educational, and **noncommercial** use — but **commercial
use requires a separate license** from the rights holder.

| Package | SPDX |
| --- | --- |
| `persona-core`, `persona-runtime`, `persona-voice` | `MIT` |
| `persona-api`, `persona-web` | `PolyForm-Noncommercial-1.0.0` |

The MIT engine never imports the PolyForm-NC app (enforced in CI by an
`import-linter` contract), so the permissive packages stay genuinely permissive.

---

## Contributing

Contributions are welcome on the three MIT engine packages (`core`,
`runtime`, `voice`) under the MIT License. Please:

1. Open an issue first if the change is non-trivial. A quick design check
   saves both sides a round-trip.
2. Follow the existing engineering style: Python 3.11+, Pydantic v2 frozen
   models on every boundary, `mypy --strict` on `persona-core`, full
   docstrings on public APIs, `ruff check` + `ruff format` clean, tests
   required for new behaviour.
3. Conventional commits (`feat:`, `fix:`, `refactor:`, `docs:`, `test:`,
   `chore:`), squash-merge to `main`.

See `pyproject.toml` for the canonical tooling configuration.

`persona-api` and `persona-web` are not accepting external contributions
yet. They're under active hardening and the surface is still moving.

---

## Roadmap

The shipped v0.1 is the floor, not the ceiling. The themes the next
releases work toward (in rough order):

- **Voice trunk completion**: turn-taking + barge-in, model reply
  producer, frontend voice client (V4-V6) so real-time two-way voice
  conversation is end-to-end usable.
- **Intelligent routing**: replace the static tier-config router with a
  signal-driven routing layer that scores each turn against model
  capabilities (cost, latency, reasoning depth, tool capability, vision,
  audio) and picks the right tier per turn.
- **Tools v2**: better tool authoring ergonomics, structured tool
  observations, tool-level budgeting and observability.
- **MCP v1**: first-class Model Context Protocol client so any MCP server
  in the wild becomes a persona-callable tool.
- **Rich output delivery**: inline rendering of images, files, diagrams,
  and other non-text artifacts in the chat surface.

Watch the [CHANGELOG](CHANGELOG.md) for what actually shipped, and the
per-package `CHANGELOG.md` files for per-surface detail.

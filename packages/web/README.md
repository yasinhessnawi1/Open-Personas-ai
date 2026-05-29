# persona-web

The Open Persona web app (spec 09). Next.js 16 (App Router) + TypeScript (strict) + Tailwind v4 + shadcn/ui, Clerk auth, and an OpenAPI-generated client against the `persona-api` (spec 08). A thin client — all business logic lives in the API.

> Standalone Node project. **Not** part of the `uv` workspace (that's `core`/`runtime`/`api`). `uv sync` does nothing here; use `pnpm`.

## Features

- **Landing** — public marketing page (`/`), auth-aware CTAs.
- **Auth** — Clerk sign-in/up/out; the `(app)` group is protected.
- **Personas** — list + detail; **authoring** (NL → frontier draft → structured form ⇄ lazy Monaco YAML → save) and **edit**.
- **Chat** — streaming SSE chat with a visible identity header, collapsible tool-call cards, and a per-turn tier badge.
- **Run viewer** — the agentic-run timeline over SSE (catch-up + reconcile-on-drop), inline ask-user, Markdown final, cancel.
- **Settings** — credit balance + per-turn usage; theme, tier-badge-visibility, and language (pseudo-locale) toggles. Real conversations list.
- **Responsive + dark mode + i18n** — usable at 375px; `next-intl` everywhere (a pseudo-locale verifies coverage).

## Requirements

- Node ≥ 20.9 (tested on 20.19), pnpm 10.x.
- A running `persona-api` for live data (see `packages/api`).

## Setup

```bash
cd packages/web
pnpm install
cp .env.example .env.local   # fill in NEXT_PUBLIC_API_BASE_URL + Clerk keys
pnpm dev                     # http://localhost:3000
```

## Scripts

| Command | What |
|---|---|
| `pnpm dev` | Dev server (Turbopack). |
| `pnpm build` | Production build (`next build`) — part of "green"; catches RSC / `"use client"` boundary errors `tsc` misses. |
| `pnpm start` | Serve the production build. |
| `pnpm typecheck` | `tsc --noEmit` (strict, no `any`). |
| `pnpm lint` | Biome (format + lint, incl. React-hooks & Next rules via Biome domains). |
| `pnpm format` | Biome auto-format. |
| `pnpm test` | Vitest (+ React Testing Library). |
| `pnpm test:e2e` | Playwright end-to-end (needs the API on :8000). |

"Done" for a UI change = `typecheck` + `lint` + `build` + `test` clean **and** the feature works in a running browser.

## E2E

`pnpm exec playwright test` runs the suite against a real browser + the live API. The harness (`e2e/`) fetches a Clerk testing token, signs up a `+clerk_test` user (OTP `424242`), saves `storageState`, and runs the page specs authed. Bring up the stack first: `docker start persona-pg` → `cd ../api && bash run-local.sh` → the web dev server (Playwright starts its own if :3000 is free). Note: the suite shares one signed-up user, so specs that assert global emptiness are written to tolerate seeded data.

## Architecture notes

- **REST** calls go through the committed, generated client (`src/lib/api/`, from the API's `/openapi.json`) — never hand-written `fetch`.
- **SSE** streams (chat, run viewer) are consumed via `fetch` + `ReadableStream` (not `EventSource`); their event shapes are **hand-mirrored** in `src/lib/sse-types.ts` (OpenAPI can't model SSE).
- **State:** TanStack Query for server state, React context for UI state. No global store.
- **i18n:** `next-intl`; every user-facing string goes through the translation function. English-only strings for v0.1 (`src/i18n/messages/en.json`).
- **Theme:** `next-themes`, class-based dark mode, system default.

See `docs/specs/spec_09/` for the spec, decisions, and task breakdown.

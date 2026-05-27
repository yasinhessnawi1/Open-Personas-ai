# Changelog

All notable changes to Open Persona are recorded here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
The project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Per-spec entries are added by the close-out phase of each spec.

---

## [Unreleased]

_Nothing here yet._

## [0.3.0] — 2026-05-27

Spec 03 close-out. Tools, MCP, and the Toolbox.

### Added
- `persona.tools.ToolDescriptor` Protocol (the metadata surface — `name`, `description`, `parameters_schema`) and `persona.tools.AsyncTool` Protocol (extends `ToolDescriptor` with `async execute(**kwargs) -> ToolResult`). Sibling to spec-01's sync `Tool` Protocol (D-03-2; spec-01's `Tool` is untouched). ([`tools/protocol.py`](packages/core/src/persona/tools/protocol.py))
- `@tool(name=..., description=...)` decorator wrapping an `async def` into an `AsyncTool`. JSON Schema synthesised via `pydantic.TypeAdapter`; argument model uses `ConfigDict(extra="forbid")` so typo'd kwargs from the model fail validation. Two catch sites — argument-validation errors AND body-raised `Exception` (not `BaseException`) — both produce `ToolResult(is_error=True, ...)`. `BaseException` propagates (D-03-5). ([`tools/protocol.py`](packages/core/src/persona/tools/protocol.py))
- `persona.tools.Toolbox` — registry + literal-only allow-list + async `dispatch`. `None` allow-list is permissive with a WARNING log (development convenience per D-03-7); production callers pass `persona.tools`. Duplicate tool names raise `ValueError`. `ToolNotAllowedError.context["allowed"]` carries a comma-joined string of available names per D-03-8. ([`tools/toolbox.py`](packages/core/src/persona/tools/toolbox.py))
- `format_tool_result(call, result, *, provider_name) -> ConversationMessage` — provider-aware formatter using a `match` statement on seven supported provider names. Anthropic (`tool_result` content block in user message), OpenAI / DeepSeek / Groq / Together (role=tool with `tool_call_id`), Ollama / local HF (shim plain-text). Unknown provider raises `ValueError` (D-03-6). ([`tools/formatting.py`](packages/core/src/persona/tools/formatting.py))
- Built-in tool `web_search` (D-03-9, D-03-10) — `make_web_search_tool(provider, api_key, http)` factory; `_SearchProvider` Protocol; `BraveSearchProvider` wired against `https://api.search.brave.com/res/v1/web/search` with `X-Subscription-Token` header; `TavilySearchProvider` and `SerpAPISearchProvider` raise `NotImplementedError` (caught by the `@tool` envelope → `ToolResult(is_error=True)`). Provider via `PERSONA_WEB_SEARCH_PROVIDER`; key via `PERSONA_WEB_SEARCH_API_KEY`. Structured results in `ToolResult.data["results"]`. ([`tools/builtin/web_search.py`](packages/core/src/persona/tools/builtin/web_search.py))
- Built-in tool `web_fetch` (D-03-11, D-03-12, D-03-24) — `httpx` + `trafilatura.extract(output_format="txt", favor_precision=True, include_comments=False, include_tables=False)`. Non-HTML content-type passes through via `Response.text`. Truncation past `max_chars` sets `truncated=True` + `data["original_length"]`. Scheme allow-list: `http`/`https` only; full SSRF guard deferred to spec 11. ([`tools/builtin/web_fetch.py`](packages/core/src/persona/tools/builtin/web_fetch.py))
- Sandbox path resolver `persona.tools._sandbox.resolve_sandbox_path(root, requested) -> Path` — pure function, no I/O. Rejects: NULL byte (D-03-15), >4096-char paths, mixed `\\` separator on POSIX, empty/whitespace, absolute paths (`PurePosixPath.is_absolute`), `.` / `./` root references, paths whose `.resolve(strict=False)` escapes `root.resolve()` (catches `..` traversal AND symlink escape). 55 adversarial tests written tests-first (Phase 1 refinement #8); two `security-reviewer` subagent passes (T09 + T10) with all findings addressed. `_preview()` strips control characters from user input before embedding in error context (security-review T09 Finding 1). ([`tools/_sandbox.py`](packages/core/src/persona/tools/_sandbox.py))
- Built-in tools `file_read` + `file_write` (D-03-16, D-03-17, D-03-18) — `make_file_read_tool(sandbox_root)` and `make_file_write_tool(sandbox_root, audit_logger, persona_id)` factories. `os.open(O_NOFOLLOW | ...)` closes the TOCTOU window between resolver and open. UTF-8 with `errors="replace"` for reads; 1 MB cap with `truncated=True` over. `file_write` mode `0o600`, emits one `ToolAuditEvent(action="write")` per successful write. Lone-surrogate `UnicodeEncodeError` and `os.write` `OSError` both caught and returned as clean `ToolResult(is_error=True, ...)` (security-review T10 Findings 5 + 10.2). ([`tools/builtin/file_read.py`](packages/core/src/persona/tools/builtin/file_read.py), [`tools/builtin/file_write.py`](packages/core/src/persona/tools/builtin/file_write.py))
- MCP client + adapter (D-03-19, D-03-20, D-03-21) — `mcp.client.streamable_http.streamablehttp_client` transport (NOT the deprecated `mcp.client.sse`). `MCPClient` uses `AsyncExitStack` for procedural-style lifecycle (`await client.connect()` / `disconnect()`). `MCPToolAdapter` wraps each discovered MCP tool as an `AsyncTool` named `mcp:<server>:<tool>` (literal allow-list per Phase 1 refinement #4). Graceful degradation `strict=False` for Toolbox auto-load. Audit events on connect / disconnect / server_unavailable; per-call dispatch audits skipped. Disconnection-like errors → `ToolResult(is_error=True, content="MCP server disconnected")`. `load_mcp_clients(servers, ...)` helper. ([`tools/mcp/client.py`](packages/core/src/persona/tools/mcp/client.py), [`tools/mcp/adapter.py`](packages/core/src/persona/tools/mcp/adapter.py))
- `persona.tools.audit` — dedicated tool-audit port (D-03-25, supersedes D-03-18's "reuse `AuditEvent`" recap). `ToolAuditEvent` Pydantic v2 model + `ToolAuditLogger(Protocol)` + `JSONLToolAuditLogger` / `MemoryToolAuditLogger` implementations. The JSONL logger documents single-process safety (security-review T10 Finding 7); hosted-service multi-process safety lands with the Postgres backend in spec 08. ([`tools/audit.py`](packages/core/src/persona/tools/audit.py))
- `build_default_toolbox(config, persona, *, tool_audit_logger) -> tuple[Toolbox, list[MCPClient]]` — composes the four built-in tools + connects MCP servers from `PersonaCoreConfig.mcp_servers_parsed`. Returns the toolbox and the MCP clients (so the caller can `await client.disconnect()` on shutdown). Graceful degradation per D-03-20. ([`tools/_factory.py`](packages/core/src/persona/tools/_factory.py))
- Two new domain exceptions: `MCPConnectionError`, `MCPServerUnavailableError` — flat under `PersonaError` per D-03-1. Re-exported from `persona.tools.errors`. ([`errors.py`](packages/core/src/persona/errors.py), [`tools/errors.py`](packages/core/src/persona/tools/errors.py))
- `persona.tools.__init__` re-exports 22 names — Protocols, `Toolbox`, `@tool`, formatter, the four built-in factories, MCP client + adapter, `build_default_toolbox`, audit Protocol + impls + event, and the five tool/MCP exceptions.

### Changed
- `persona.schema.tools.ToolResult` additively extended with `data: dict[str, Any] | None = None` and `truncated: bool = False` (D-03-3). `extra="forbid"` enforces that there is no separate `error` field — `is_error=True` + `content` is the single failure-truth.
- `persona.backends.types.tool_spec_from_tool()` parameter widened from `Tool` to `ToolDescriptor` — strictly additive (every `Tool` is a `ToolDescriptor`; every `AsyncTool` is too). No breaking change to spec-02's call sites.
- `PersonaCoreConfig` gained four spec-03 fields: `web_search_provider: Literal["brave", "tavily", "serpapi"]`, `web_search_api_key: SecretStr | None`, `tools_sandbox_root: Path` (default `./.persona_work` per D-03-23), `mcp_servers: str` (raw env value; the parsed dict is exposed via the `mcp_servers_parsed` property because Pydantic Settings JSON-pre-parses `dict[str, str]` env vars before validators run). ([`config.py`](packages/core/src/persona/config.py))
- `packages/core/pyproject.toml` — added `trafilatura>=2.0,<3` (web_fetch) and `mcp>=1.0,<2` (MCP client). Both core deps per D-03-12; transitive trees documented in [`docs/specs/spec_03/research.md`](docs/specs/spec_03/research.md) §2-3.
- `.env.example` — renamed `PERSONA_SEARCH_*` → `PERSONA_WEB_SEARCH_*` per Phase 1 refinement #7 (futureproofs against vector/code search later); added `PERSONA_TOOLS_SANDBOX_ROOT` and `PERSONA_MCP_SERVERS`.
- `packages/core/SPEC.md` — "Tools, MCP, and the Toolbox (Spec 03)" subsection added.

### Tests
- **214 new unit tests** across `tests/unit/tools/` (11 errors + 18 protocol + 20 decorator + 36 formatting + 20 toolbox + 17 web_search + 16 web_fetch + 55 sandbox + 30 file tools + 12 MCP adapter + 11 MCP client + 22 factory/config).
- Two `security-reviewer` subagent passes: T09 (sandbox resolver, 4 findings) + T10 (file tools, 10 findings — 1 HIGH, 2 MEDIUM, others LOW/accepted-risk). All actionable findings addressed in code; accepted-risk findings documented for spec 11.
- **682 unit + 28 integration + 26 contract = 736 total tests, all green.**
- All checks: `ruff check`, `ruff format --check`, `mypy --strict packages/core/src` clean (61 source files; was 47 after spec 02).

### Documentation
- `docs/specs/spec_03/{spec_03_tools.md, spec_03_kickoff.md, tasks.md, tasks.yaml, research.md, decisions.md, state.md, handover.md, README.md, closeout.md}` — full lifecycle of Spec 03 captured.
- D-03-1..D-03-25 added to root [`docs/DECISIONS.md`](docs/DECISIONS.md).

## [0.2.0] — 2026-05-27

Spec 02 close-out. Model backends and provider abstraction.

### Added
- `persona.backends.ChatBackend` async Protocol with `chat()` (single-shot) + `chat_stream()` (`AsyncIterator[StreamChunk]`). ([`backends/protocol.py`](packages/core/src/persona/backends/protocol.py))
- `OpenAICompatibleBackend` — unified backend for Anthropic (via `anthropic` SDK) and OpenAI / DeepSeek / Groq / Together (via `openai.AsyncOpenAI` with per-provider `base_url`). Native tool calling where the provider supports it; prompt-based JSON-block shim fallback. ([`backends/openai_compat.py`](packages/core/src/persona/backends/openai_compat.py))
- `OllamaBackend` — raw `httpx` to a local Ollama instance at `/api/chat`; lazy client; opt-in native tools (`use_native_tools=True`); explicit `ping()` health check; `aclose()` for lifecycle. ([`backends/ollama.py`](packages/core/src/persona/backends/ollama.py))
- `HFLocalBackend` behind `persona-core[local]` extras — lazy weight load via `asyncio.Lock`-guarded `_ensure_loaded()`; 4-bit NF4 / 8-bit / fp16 quantisation; Gemma-2 system-role fold + eager attention; `generation_config` override; `AsyncTextIteratorStreamer` for async streaming with `_CancellableStoppingCriteria`. ([`backends/hf_local.py`](packages/core/src/persona/backends/hf_local.py))
- Five new domain exceptions: `ProviderError`, `AuthenticationError`, `RateLimitError`, `ModelNotFoundError`, `BackendTimeoutError` — all subclasses of `PersonaError`, carry structured `context` per the engineering standards. ([`backends/errors.py`](packages/core/src/persona/backends/errors.py))
- Prompt-based tool-calling shim (`{"tool": "name", "args": {...}}` JSON blocks) with fail-safe parser (D-02-14). ([`backends/_tool_shim.py`](packages/core/src/persona/backends/_tool_shim.py))
- `BackendConfig` (Pydantic Settings, `PERSONA_*` env-only) with `from_env(prefix=...)` for tier-specific overrides (used by spec 05). ([`backends/config.py`](packages/core/src/persona/backends/config.py))
- `load_backend(BackendConfig)` factory + `persona.backends` package re-exports. ([`backends/__init__.py`](packages/core/src/persona/backends/__init__.py), [`backends/_factory.py`](packages/core/src/persona/backends/_factory.py))
- Response types: `ChatResponse`, `StreamChunk`, `TokenUsage`, `ToolSpec`, `ToolCallDelta` — Pydantic v2 frozen + `extra="forbid"` (D-02-2). `tool_spec_from_tool()` helper bridges spec-01's `Tool` Protocol. ([`backends/types.py`](packages/core/src/persona/backends/types.py))
- CLI: `persona chat` now wires through `load_backend(BackendConfig())` and streams via `chat_stream()`; `EchoBackend` placeholder deleted (D-02-12). ([`cli/chat_cmd.py`](packages/core/src/persona/cli/chat_cmd.py))
- Test helper `MockChatBackend` in `tests/_mock_backend.py` for CLI / integration tests (replaces deleted `_echo.py`).
- Contract test suite ([`tests/contract/test_chat_backend_contract.py`](packages/core/tests/contract/test_chat_backend_contract.py)) — 26 parametrised tests across 4 backend variants verifying Protocol compliance, chat shape, streaming, fail-fast auth, and tool-call round-trip.

### Changed
- `packages/core/pyproject.toml` — added `anthropic>=0.30,<1` and `openai>=1.30,<2` as core dependencies; `httpx>=0.27,<1` (parked under D-01-11) now live.
- `.env.example` — added `PERSONA_PROVIDER`, per-provider key vars, `PERSONA_BASE_URL`, `PERSONA_REQUEST_TIMEOUT_S`, `PERSONA_DOTENV_LOAD`, and HF local vars.
- `packages/core/SPEC.md` — model backends subsection added.

### Removed
- `packages/core/src/persona/cli/_echo.py` (deleted per D-02-12). Production no longer ships a fake backend; tests inject their own.

### Tests
- 414 unit (was 210; +204 new in `tests/unit/backends/`) + 28 integration + 26 contract = **468 total green**.
- New file: `tests/contract/test_chat_backend_contract.py` runs the same assertions against every backend variant.
- All checks: `ruff check`, `ruff format --check`, `mypy --strict packages/core/src` clean (47 source files).

### Documentation
- `docs/specs/spec_02/{spec_02_backends.md, tasks.md, tasks.yaml, research.md, decisions.md, state.md, handover.md, README.md, closeout.md}` — full lifecycle of Spec 02 captured.
- D-02-1..D-02-18 added to root [`docs/DECISIONS.md`](docs/DECISIONS.md).

## [0.1.0] — 2026-05-27

First spec close-out. Foundation of `persona-core`.

### Added
- v1.0 persona YAML schema (Pydantic v2, frozen, `extra="forbid"`) covering identity, self-facts, worldview, episodic, routing, embedding, tools, skills. ([`schema/persona.py`](packages/core/src/persona/schema/persona.py))
- `PersonaChunk` with deterministic SHA-256 `content_hash`, tz-aware UTC datetimes, and `ChunkProvenance` for the version chain. ([`schema/chunks.py`](packages/core/src/persona/schema/chunks.py))
- Three-source persona update model (`system` / `user` / `persona_self`) with per-store policy table. Versioned append-only updates with `history` and `rollback`. ([`stores/policy.py`](packages/core/src/persona/stores/policy.py), [`stores/versioning.py`](packages/core/src/persona/stores/versioning.py))
- `MemoryStore` protocol + four concrete typed stores: `IdentityStore`, `SelfFactsStore`, `WorldviewStore`, `EpisodicStore`. Episodic decay is query-time exponential (`tau=24h` default).
- `ChromaMemoryStore` transport with deterministic per-`(persona, store_kind)` collection naming, cosine-distance HNSW, SQLite query-batch cap, and provenance serialised into Chroma metadata.
- `PersonaRegistry` — load YAML, validate, index author-time chunks; idempotent re-load.
- `ConversationHistoryManager` — summarise-and-compact (`compact_every=10`, `keep_recent=5`). Summariser injected.
- Per-component logging via `loguru` (`persona.logging.get_logger`), idempotent sink configuration (D-01-7).
- JSONL audit log behind an `AuditLogger` Protocol; every store mutation emits exactly one `AuditEvent`. (`MemoryAuditLogger` for tests.)
- Typer CLI: `persona init`, `persona validate`, `persona chat` (placeholder `EchoBackend`), `persona audit`, `persona run` (stub for spec 06).
- `py.typed` marker shipped in the wheel; structured-context domain exceptions; CHANGELOG; .editorconfig; pre-commit hooks (ruff, ruff-format, mypy --strict, pytest --collect-only).

### Infrastructure
- Root `pyproject.toml` declares workspace members as root dependencies so a plain `uv sync` installs the whole monorepo.
- `[tool.uv.sources]` blocks in `packages/runtime/pyproject.toml` and `packages/api/pyproject.toml` (required by uv).
- Root `conftest.py` prepends each workspace `src/` to `sys.path` to work around CPython 3.13's hidden-`_editable_impl_` `.pth` skip.

### Tests
- 210 unit + 28 integration tests across 11 test files. 10 valid + 10 invalid persona YAML fixtures. Pure-function policy table tested in isolation; concrete stores tested against real ChromaDB.

### Documentation
- `docs/specs/spec_01/{spec_01_core.md, tasks.md, tasks.yaml, research.md, decisions.md, state.md, handover.md, README.md, closeout.md}` — full lifecycle of Spec 01 captured.

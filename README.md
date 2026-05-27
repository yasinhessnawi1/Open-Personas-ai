# Open Persona

An open-source platform for building and running AI personas with typed memory, multi-model routing, and agentic task execution.

## Repository structure

```
packages/
  core/       persona-core — the open-source library (Apache 2.0)
  runtime/    persona-runtime — the generation loop, router, and agentic engine
  api/        persona-api — the hosted FastAPI service
  web/        persona-web — the Next.js web application
specs/        specification documents for each component
docs/         research notes, decisions, and project documentation
```

## Development setup

```bash
uv sync
uv run pytest
uv run mypy packages/core/src
uv run ruff check
```

## License

`packages/core/` is licensed under Apache 2.0. All other packages are private.

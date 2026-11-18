# Contributing

## Setup

You need [uv](https://docs.astral.sh/uv/). Node is only needed if you change the UI.

```bash
uv sync                      # creates .venv with the dev tools and all optional readers
uv run spektrify view --demo
```

## Checks (the same ones CI runs)

```bash
uv run ruff check --fix src tests && uv run ruff format src tests
uv run ty check
uv run pytest
```

Optional: `uvx pre-commit install` runs ruff on every commit.

## UI

```bash
cd frontend && npm ci
uv run spektrify view --demo --no-browser &   # API on :8765
npm run dev                                   # hot reload on :5173, proxies /api
npm run build                                 # writes src/spektrify/static; commit it
```

CI fails if `src/spektrify/static` doesn't match a fresh build, so always commit the build.

## Guidelines

- Keep layers apart: readers (`io/`) don't know about the server, compute backends only see a
  `Cube`, routes are plain functions, and the UI talks to the backend only through
  `frontend/src/lib/api.js`. [docs/architecture.md](docs/architecture.md) describes the
  boundaries.
- Extend through the registries (`register_reader`, `register_demosaicer`, `register_step`,
  `register_backend`) instead of adding special cases.
- Add a test with every behaviour change. Keep heavy dependencies optional and import them
  inside the function that needs them.
- Commit messages: imperative mood, with a short summary line. Add user-visible changes to
  `CHANGELOG.md`.

#!/usr/bin/env bash
# Build the online learn-mode demo into build/site: the UI in its static mode, plus the
# precomputed data it reads instead of a server. Used by Vercel and CI; see docs/site.md.
set -euo pipefail
cd "$(dirname "$0")/.."

if ! command -v uv >/dev/null; then # e.g. on Vercel: install uv (it also fetches Python 3.12)
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

(cd frontend && npm ci --no-audit --no-fund && npm run build:site)
uv run --locked python -m spektrify.server.snapshot build/site/data

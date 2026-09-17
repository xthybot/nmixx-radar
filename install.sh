#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Install it first:"
  echo "curl -LsSf https://astral.sh/uv/install.sh | sh"
  exit 1
fi

uv sync --frozen

echo
echo "Installed. Start the site with:"
echo "uv run uvicorn app.main:app --host 0.0.0.0 --port 32765"

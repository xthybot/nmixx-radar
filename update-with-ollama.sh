#!/usr/bin/env bash
set -euo pipefail

export OLLAMA_HOST="${OLLAMA_HOST:-http://127.0.0.1:11434}"
export OLLAMA_MODEL="${OLLAMA_MODEL:-qwen3.8:27b-q8-Customize_80k_-1}"
if ! curl -fsS -m 5 "$OLLAMA_HOST/api/tags" >/dev/null 2>&1; then
  unset OLLAMA_MODEL
  if [ -n "${OPENAI_API_KEY:-}" ] && [ -z "${OPENAI_MODEL:-}" ]; then
    export OPENAI_MODEL="${OPENAI_MODEL:-gpt-5.5}"
  elif [ -z "${AI_REVIEW_COMMAND:-}" ] && [ -z "${OPENAI_API_KEY:-}" ]; then
    export USE_HEURISTIC_REVIEW=1
  fi
fi

uv run python -m app.update_watcher "$@"

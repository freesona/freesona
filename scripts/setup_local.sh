#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [ ! -f .env ]; then
  cp .env.sample .env
  echo "Created .env from .env.sample. Review it and fill in your real IDs and provider keys before running the bot."
fi

set -a
source .env
set +a

REQUIRED_VARS=(BOT_TOKEN CHANNEL_ID AI_PROVIDER)
for name in "${REQUIRED_VARS[@]}"; do
  if [ -z "${!name:-}" ] || [[ "${!name}" == "YOUR_"* ]]; then
    echo "Missing or placeholder value for $name in .env" >&2
    exit 1
  fi
done

case "$AI_PROVIDER" in
  gemini) [ -n "${GOOGLE_API_KEY:-}" ] || { echo "GOOGLE_API_KEY is required when AI_PROVIDER=gemini" >&2; exit 1; } ;;
  openai) [ -n "${OPENAI_API_KEY:-}" ] || { echo "OPENAI_API_KEY is required when AI_PROVIDER=openai" >&2; exit 1; } ;;
  ollama) [ -n "${OLLAMA_BASE_URL:-}" ] || export OLLAMA_BASE_URL="http://localhost:11434/api/chat" ;;
  nim) [ -n "${NVIDIA_API_KEY:-}" ] || { echo "NVIDIA_API_KEY is required when AI_PROVIDER=nim" >&2; exit 1; } ;;
  azure) [ -n "${AZURE_AI_KEY:-}" ] || { echo "AZURE_AI_KEY is required when AI_PROVIDER=azure" >&2; exit 1; } ; [ -n "${AZURE_AI_BASE_URL:-}" ] || { echo "AZURE_AI_BASE_URL is required when AI_PROVIDER=azure" >&2; exit 1; } ;;
  groq) [ -n "${GROQ_API_KEY:-}" ] || { echo "GROQ_API_KEY is required when AI_PROVIDER=groq" >&2; exit 1; } ;;
  openrouter) [ -n "${OPENROUTER_API_KEY:-}" ] || { echo "OPENROUTER_API_KEY is required when AI_PROVIDER=openrouter" >&2; exit 1; } ;;
  *) echo "Unsupported AI_PROVIDER '$AI_PROVIDER'. Supported values: gemini, openai, ollama, nim, azure, groq, openrouter." >&2; exit 1 ;;
esac

if ! [[ "$CHANNEL_ID" =~ ^[0-9]+$ ]]; then
  echo "CHANNEL_ID must be a numeric Discord channel snowflake." >&2
  exit 1
fi

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt >/dev/null

python scripts/check_project.py
python main.py

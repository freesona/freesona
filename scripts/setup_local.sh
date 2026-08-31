#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

load_env_defaults() {
  python3 - <<'PY'
import re
from pathlib import Path

env_path = Path('.env')

for raw_line in env_path.read_text(encoding='utf-8').splitlines():
    line = raw_line.strip()
    if not line or line.startswith('#'):
        continue

    if line.startswith('export '):
        line = line[7:].lstrip()

    if '=' not in line:
        continue

    key, value = line.split('=', 1)
    key = key.strip()
    if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', key):
        continue

    value = value.strip()
    if value[:1] in {'"', "'"} and value[-1:] == value[:1]:
        value = value[1:-1]
    else:
        value = re.split(r'#(?=\s)', value, maxsplit=1)[0].rstrip()

    print(f'{key}={value}')
PY
}

# ASCII Art Banner
print_banner() {
cat << 'EOF'

                    IIIII
                    II II
                    II II
                III       III
               II  IIIIIII  II
              I  IIIIIIIIIII  II
             I  IIIIIIIIIIIII  I
             I  IIIIIIIIIIIII  I
          III   IIIIIIIIIIIII    II
        II   II  IIIIIIIIIII  II   II
      II  IIIIII   IIIIIII   IIIIII  II
     II  IIIIIIIIII       IIIIIIIIIII  I       IIIIIIIIII
    I  IIIIIIIIIII  IIIII  IIIIIIIIIII  I      IIIIIIIIII
   I  IIIIIIIIIIII IIIIIII IIIIIIIIIIII  I     III
  II IIIIIIIIIIII  IIIIIII  IIIIIIIIIIII II    III       IIIIIIII IIIIIIII    IIIIIIIII   IIIIIIII    IIIIIIII   III IIIIII   IIIIIIII
  I  IIIIIIIIIII  IIIIIIIII  IIIIIIIIIII  I    IIIIIIIII IIIII   III    IIII IIII   III IIII    III IIIII   IIII IIII   IIII III    III
 II  IIIII  IIII IIIIIIIIIII  III  IIIII  II   III       IIII   IIIIIIIIIIIIIIIIIIIIIIII  IIIIIIII  III      III III     III   IIIIIIII
 II  IIIII I       IIIIIII       I IIIII  II   III       IIII   III         IIII            IIIIIII III      III III     III IIII  IIII
 II  IIII  IIIIIIIIIIIIIIIIIIIIIII  IIII  II   III       IIII    IIII  IIII  IIII   IIII IIII   III  IIII  IIIII III     III III   IIIII
 II  IIII IIIIIIIIIIIIIIIIIIIIIIIII IIII  I    III       IIII     IIIIIIII     IIIIIII    IIIIIIII    IIIIIIII   III     III IIIIIII III
EOF
}
print_banner

echo ""
echo "====================================================="
echo "  Freesona - Self-Hosted Discord AI Framework Setup  "
echo "====================================================="
echo ""

# If .env exists, load it for defaults
if [ -f .env ]; then
  while IFS= read -r assignment; do
    export "$assignment"
  done < <(load_env_defaults)
fi

# Interactive prompts for required values
echo "--- Required Configuration ---"
echo ""

# BOT_TOKEN
read -p "Discord Bot Token [${BOT_TOKEN:-YOUR_DISCORD_BOT_TOKEN}]: " input
BOT_TOKEN="${input:-${BOT_TOKEN:-YOUR_DISCORD_BOT_TOKEN}}"

# CHANNEL_ID
read -p "Log Channel ID (numeric Discord snowflake) [${CHANNEL_ID:-YOUR_LOG_CHANNEL_ID}]: " input
CHANNEL_ID="${input:-${CHANNEL_ID:-YOUR_LOG_CHANNEL_ID}}"

# BOT_NAME
read -p "Bot Name [${BOT_NAME:-Freesona}]: " input
BOT_NAME="${input:-${BOT_NAME:-Freesona}}"

# AI_PROVIDER
echo ""
echo "Available AI Providers: gemini, openai, ollama, nim, azure, groq, openrouter"
read -p "AI Provider [${AI_PROVIDER:-gemini}]: " input
AI_PROVIDER="${input:-${AI_PROVIDER:-gemini}}"

# Provider-specific configuration
echo ""
echo "--- Provider Configuration ---"
echo "For each provider, you'll need an API key. Here's where to get them:"
echo "  gemini:    https://aistudio.google.com/app/apikey (Google AI Studio)"
echo "  openai:    https://platform.openai.com/api-keys (OpenAI Platform)"
echo "  ollama:    Run locally - no API key needed (default: http://localhost:11434)"
echo "  nim:       https://build.nvidia.com/ (NVIDIA NIM API keys)"
echo "  azure:     https://portal.azure.com/ (Azure AI Foundry / OpenAI Service)"
echo "  groq:      https://console.groq.com/keys (Groq Console)"
echo "  openrouter: https://openrouter.ai/keys (OpenRouter)"
echo ""
case "$AI_PROVIDER" in
  gemini)
    read -p "Google API Key (Gemini) [${GOOGLE_API_KEY:-YOUR_GEMINI_API_KEY}]: " input
    GOOGLE_API_KEY="${input:-${GOOGLE_API_KEY:-YOUR_GEMINI_API_KEY}}"
    ;;
  openai)
    read -p "OpenAI API Key [${OPENAI_API_KEY:-}]: " input
    OPENAI_API_KEY="${input:-${OPENAI_API_KEY:-}}"
    read -p "OpenAI Base URL [${OPENAI_BASE_URL:-https://api.openai.com/v1/chat/completions}]: " input
    OPENAI_BASE_URL="${input:-${OPENAI_BASE_URL:-https://api.openai.com/v1/chat/completions}}"
    ;;
  ollama)
    read -p "Ollama Base URL [${OLLAMA_BASE_URL:-http://localhost:11434/api/chat}]: " input
    OLLAMA_BASE_URL="${input:-${OLLAMA_BASE_URL:-http://localhost:11434/api/chat}}"
    ;;
  nim)
    read -p "NVIDIA API Key [${NVIDIA_API_KEY:-}]: " input
    NVIDIA_API_KEY="${input:-${NVIDIA_API_KEY:-}}"
    read -p "NVIDIA NIM Base URL [${NVIDIA_NIM_BASE_URL:-https://integrate.api.nvidia.com/v1/chat/completions}]: " input
    NVIDIA_NIM_BASE_URL="${input:-${NVIDIA_NIM_BASE_URL:-https://integrate.api.nvidia.com/v1/chat/completions}}"
    ;;
  azure)
    read -p "Azure AI Key [${AZURE_AI_KEY:-}]: " input
    AZURE_AI_KEY="${input:-${AZURE_AI_KEY:-}}"
    read -p "Azure AI Base URL [${AZURE_AI_BASE_URL:-}]: " input
    AZURE_AI_BASE_URL="${input:-${AZURE_AI_BASE_URL:-}}"
    ;;
  groq)
    read -p "Groq API Key [${GROQ_API_KEY:-}]: " input
    GROQ_API_KEY="${input:-${GROQ_API_KEY:-}}"
    ;;
  openrouter)
    read -p "OpenRouter API Key [${OPENROUTER_API_KEY:-}]: " input
    OPENROUTER_API_KEY="${input:-${OPENROUTER_API_KEY:-}}"
    read -p "OpenRouter Site URL [${OPENROUTER_SITE_URL:-}]: " input
    OPENROUTER_SITE_URL="${input:-${OPENROUTER_SITE_URL:-}}"
    read -p "OpenRouter Site Name [${OPENROUTER_SITE_NAME:-Freesona}]: " input
    OPENROUTER_SITE_NAME="${input:-${OPENROUTER_SITE_NAME:-Freesona}}"
    ;;
  *)
    echo "Unsupported AI_PROVIDER: $AI_PROVIDER"
    exit 1
    ;;
esac

# Optional: Model override
read -p "Model Name (override default for provider) [${MODEL_NAME:-}]: " input
MODEL_NAME="${input:-${MODEL_NAME:-}}"

# Optional: Model Temperature (0.0 = deterministic, 1.0 = creative, 2.0 = very creative)
read -p "Model Temperature 0.0-2.0 [${MODEL_TEMPERATURE:-0.7}]: " input
MODEL_TEMPERATURE="${input:-${MODEL_TEMPERATURE:-0.7}}"

# Optional: ChromaDB
read -p "ChromaDB Collection [${CHROMA_COLLECTION:-freesona}]: " input
CHROMA_COLLECTION="${input:-${CHROMA_COLLECTION:-freesona}}"
read -p "ChromaDB Persist Directory [${CHROMA_PERSIST_DIRECTORY:-./.chroma}]: " input
CHROMA_PERSIST_DIRECTORY="${input:-${CHROMA_PERSIST_DIRECTORY:-./.chroma}}"

# Optional: Knowledge Base
read -p "Enable Knowledge Base? (true/false) [${KB_ENABLED:-true}]: " input
KB_ENABLED="${input:-${KB_ENABLED:-true}}"
if [[ "$KB_ENABLED" == "true" ]]; then
  echo "  (KB Top K = how many knowledge base entries to retrieve; higher = more context, lower = faster)"
  read -p "Knowledge Base Results Count [${KB_TOP_K:-5}]: " input
  KB_TOP_K="${input:-${KB_TOP_K:-5}}"
fi

# Optional: Complimentary tokens
echo ""
echo "--- Optional Integrations (press Enter to skip) ---"
read -p "MVSEP API Key [${MVSEP_API_KEY:-YOUR_MVSEP_API_KEY}]: " input
MVSEP_API_KEY="${input:-${MVSEP_API_KEY:-YOUR_MVSEP_API_KEY}}"
read -p "MVSEP Webhook URL [${MVSEP_WEBHOOK_URL:-https://your-public-host.example.com/webhooks/mvsep}]: " input
MVSEP_WEBHOOK_URL="${input:-${MVSEP_WEBHOOK_URL:-https://your-public-host.example.com/webhooks/mvsep}}"
read -p "Wolfram AppID Short [${WOLFRAM_APPID_SHORT:-YOUR_WOLFRAM_APPID_SHORT}]: " input
WOLFRAM_APPID_SHORT="${input:-${WOLFRAM_APPID_SHORT:-YOUR_WOLFRAM_APPID_SHORT}}"
read -p "Wolfram AppID LLM [${WOLFRAM_APPID_LLM:-YOUR_WOLFRAM_APPID_LLM}]: " input
WOLFRAM_APPID_LLM="${input:-${WOLFRAM_APPID_LLM:-YOUR_WOLFRAM_APPID_LLM}}"

# Write .env file
echo ""
echo "Writing configuration to .env..."
cat > .env << ENVEOF
# HTTP Server
HTTP_PORT=10000

# Discord
BOT_TOKEN=${BOT_TOKEN}
CHANNEL_ID=${CHANNEL_ID}
BOT_NAME=${BOT_NAME}

# AI Provider
AI_PROVIDER=${AI_PROVIDER}
AI_PROVIDER_MODEL=${MODEL_NAME}
MODEL_NAME=${MODEL_NAME}
MODEL_TEMPERATURE=${MODEL_TEMPERATURE}
GOOGLE_API_KEY=${GOOGLE_API_KEY}

# Provider API keys (set the one matching your AI_PROVIDER)
OPENAI_API_KEY=${OPENAI_API_KEY:-}
OPENAI_BASE_URL=${OPENAI_BASE_URL:-https://api.openai.com/v1/chat/completions}
OLLAMA_BASE_URL=${OLLAMA_BASE_URL:-http://localhost:11434/api/chat}
NVIDIA_API_KEY=${NVIDIA_API_KEY:-}
NVIDIA_NIM_BASE_URL=${NVIDIA_NIM_BASE_URL:-https://integrate.api.nvidia.com/v1/chat/completions}
AZURE_AI_KEY=${AZURE_AI_KEY:-}
AZURE_AI_BASE_URL=${AZURE_AI_BASE_URL:-}
GROQ_API_KEY=${GROQ_API_KEY:-}
OPENROUTER_API_KEY=${OPENROUTER_API_KEY:-}
OPENROUTER_SITE_URL=${OPENROUTER_SITE_URL:-}
OPENROUTER_SITE_NAME=${OPENROUTER_SITE_NAME:-Freesona}

# ChromaDB (optional — required for knowledge base retrieval)
CHROMA_COLLECTION=${CHROMA_COLLECTION}
CHROMA_PERSIST_DIRECTORY=${CHROMA_PERSIST_DIRECTORY}

# Knowledge Base (optional)
KB_ENABLED=${KB_ENABLED}
KB_TOP_K=${KB_TOP_K:-5}

# Complimentary tokens
MVSEP_API_KEY=${MVSEP_API_KEY}
MVSEP_WEBHOOK_URL=${MVSEP_WEBHOOK_URL}
MVSEP_WEBHOOK_SEND_MAIL_ON_ERROR=false
WOLFRAM_APPID_SHORT=${WOLFRAM_APPID_SHORT}
WOLFRAM_APPID_LLM=${WOLFRAM_APPID_LLM}

# File paths (local)
AI_PERSONA_FILE=persona.txt
AI_PERSONA_JSON_FILE=persona.json
AI_PERSONAS_FILE=personas.json
AI_PERSONA=""
CONFIG_FILE_PATH=config.json
MEMORY_FILE_PATH=memory.db
WARNINGS_FILE_PATH=warnings.db
ANNIVERSARIES_FILE_PATH=anniversaries.db
CANON_FILE_PATH=canon.db
CHARACTER_MEMORY_FILE_PATH=character_memory.db
ENVEOF

echo "Configuration saved to .env"
echo ""

# Ensure config.json exists with default values
if [ ! -f config.json ]; then
    echo "Creating default config.json..."
    python3 - <<'PY'
import sys
sys.path.insert(0, '.')
from utils.config import save_config, DEFAULT_CONFIG
save_config(DEFAULT_CONFIG)
PY
fi

# Validate required fields
if [[ "$BOT_TOKEN" == "YOUR_DISCORD_BOT_TOKEN" ]] || [ -z "$BOT_TOKEN" ]; then
  echo "Warning: BOT_TOKEN not set. The bot will not start without a valid token."
fi

if ! [[ "$CHANNEL_ID" =~ ^[0-9]+$ ]]; then
  echo "Warning: CHANNEL_ID must be a numeric Discord channel snowflake."
fi

case "$AI_PROVIDER" in
  gemini) [[ -z "$GOOGLE_API_KEY" || "$GOOGLE_API_KEY" == "YOUR_GEMINI_API_KEY" ]] && echo "Warning: GOOGLE_API_KEY not set for Gemini provider." ;;
  openai) [[ -z "$OPENAI_API_KEY" ]] && echo "Warning: OPENAI_API_KEY not set for OpenAI provider." ;;
  ollama) : ;;
  nim) [[ -z "$NVIDIA_API_KEY" ]] && echo "Warning: NVIDIA_API_KEY not set for NIM provider." ;;
  azure) [[ -z "$AZURE_AI_KEY" || -z "$AZURE_AI_BASE_URL" ]] && echo "Warning: AZURE_AI_KEY and AZURE_AI_BASE_URL required for Azure provider." ;;
  groq) [[ -z "$GROQ_API_KEY" ]] && echo "Warning: GROQ_API_KEY not set for Groq provider." ;;
  openrouter) [[ -z "$OPENROUTER_API_KEY" ]] && echo "Warning: OPENROUTER_API_KEY not set for OpenRouter provider." ;;
  *) echo "Warning: Unknown AI_PROVIDER: $AI_PROVIDER" ;;
esac

echo ""
echo "Setting up Python environment..."
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
python -m pip install -r requirements.txt >/dev/null

# Optional delphitools CLI installation
read -p "Do you want to install delphitools CLI (requires Rust)? [y/N] " install_dt
if [[ "$install_dt" =~ ^[Yy]$ ]]; then
    if ! command -v rustc >/dev/null 2>&1; then
        echo "Rust toolchain not found. Install it from https://www.rust-lang.org/tools/install"
    else
        cargo install delphitools-cli || echo "Failed to install delphitools-cli via cargo."
    fi
fi

echo ""
echo "Running project checks..."
python scripts/check_project.py

echo ""
echo "====================================================="
echo "         Setup complete! Starting Freesona...        "
echo "====================================================="
echo ""
python main.py

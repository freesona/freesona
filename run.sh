#!/usr/bin/env bash
# run.sh - Run Freesona bot without sourcing .venv
# Assumes setup_local.sh has been run and .venv exists with dependencies installed.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# Check if setup has been completed
CONFIG_FILE="config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: $CONFIG_FILE not found. Please run ./scripts/setup_local.sh first."
    exit 1
fi

# Check if .venv exists
if [ ! -d ".venv" ]; then
    echo "Error: .venv directory not found. Please run ./scripts/setup_local.sh first."
    exit 1
fi

# Activate virtual environment and run
source .venv/bin/activate
exec python main.py

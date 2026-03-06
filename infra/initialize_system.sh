#!/usr/bin/env bash
# VisionArk System Initialization
# Linux/macOS equivalent of initialize_system.bat

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
CORE_ENV_PATH="$PROJECT_ROOT/.env.core"
EDGE_ENV_PATH="$PROJECT_ROOT/.env.edge"

export CORE_ENV_FILE="../.env.core"
export EDGE_ENV_FILE="../.env.edge"
if [[ ! -f "$CORE_ENV_PATH" ]]; then
    echo "ERROR: $CORE_ENV_PATH not found."
    exit 1
fi
if [[ ! -f "$EDGE_ENV_PATH" ]]; then
    echo "ERROR: $EDGE_ENV_PATH not found."
    exit 1
fi

echo "========================================"
echo "VISION ARK - System Initialization"
echo "[WARNING] This will wipe ALL user data and registrations!"
echo "========================================"
echo

read -rp "Are you sure you want to proceed? (y/n): " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Initialization cancelled."
    exit 0
fi

echo
echo "[1/4] Stopping and removing Docker containers and volumes..."
docker-compose -f "$COMPOSE_FILE" down -v

echo
echo "[2/4] Wiping host data directories..."
if [[ -d "$PROJECT_ROOT/data" ]]; then
    echo "Cleaning data/..."
    rm -rf "${PROJECT_ROOT:?}/data/"*
else
    echo "data/ not found — skipping."
fi

echo
echo "[3/4] Rebuilding and starting services..."
docker-compose -f "$COMPOSE_FILE" --profile all up -d --build

echo
echo "[4/4] Verification..."
docker-compose -f "$COMPOSE_FILE" ps

echo
echo "System has been initialized."
echo "All test data, user accounts, and directories have been cleared."
echo "The global system prompt will be re-populated from source code on next registration."
echo
echo "Done!"

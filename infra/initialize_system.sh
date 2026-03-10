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
echo "[1/6] Stopping and removing Docker containers and volumes..."
docker-compose -f "$COMPOSE_FILE" --profile all down -v --remove-orphans

echo
echo "[2/6] Removing residual PostgreSQL volumes..."
mapfile -t PG_VOLUMES < <(docker volume ls --format '{{.Name}}' | grep -E '(^|_)postgres_data($|_)' || true)
if [[ ${#PG_VOLUMES[@]} -gt 0 ]]; then
    for vol in "${PG_VOLUMES[@]}"; do
        echo "Removing volume: $vol"
        docker volume rm -f "$vol" >/dev/null || true
    done
else
    echo "No postgres_data volumes found - skipping."
fi

echo
echo "[3/6] Wiping host data directories..."
if [[ -d "$PROJECT_ROOT/data" ]]; then
    echo "Cleaning data/..."
    rm -rf "${PROJECT_ROOT:?}/data/"*
else
    echo "data/ not found - skipping."
fi

if [[ -d "$PROJECT_ROOT/logs" ]]; then
    echo "Cleaning logs/..."
    rm -rf "${PROJECT_ROOT:?}/logs/"*
else
    echo "logs/ not found - skipping."
fi

echo
echo "[4/6] Migration mode..."
echo "_run_migrations is now a placeholder (no legacy migration replay)."

echo
echo "[5/6] Rebuilding and starting services..."
docker-compose -f "$COMPOSE_FILE" --profile all up -d --build

echo
echo "[6/6] Verification..."
docker-compose -f "$COMPOSE_FILE" ps

echo
echo "System has been initialized."
echo "All test data, user accounts, and directories have been cleared."
echo "The global system prompt will be re-populated from source code on next registration."
echo
echo "Done!"

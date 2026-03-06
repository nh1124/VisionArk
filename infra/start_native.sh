#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NATIVE_ROOT="$SCRIPT_DIR/../core/native"

echo "=== VisionArk Native Dev ==="

cleanup() {
    if [[ -n "${DAEMON_PID:-}" ]]; then
        kill "$DAEMON_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

echo "[1/2] Starting daemon..."
cd "$NATIVE_ROOT/daemon"
VISIONARK_API_URL="${VISIONARK_API_URL:-http://localhost:8000}" \
VISIONARK_TOKEN="${VISIONARK_TOKEN:-}" \
cargo run &
DAEMON_PID=$!

echo "[2/2] Starting Tauri desktop..."
cd "$NATIVE_ROOT/desktop"
if [[ ! -d node_modules ]]; then
    echo "    node_modules not found, running npm install..."
    npm install
fi
cargo tauri dev

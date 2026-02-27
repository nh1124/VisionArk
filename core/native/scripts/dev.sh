#!/usr/bin/env bash
# VisionArk Native App — development startup script
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$SCRIPT_DIR/.."

echo "=== VisionArk Native Dev ==="

# Start daemon in background
echo "[1/2] Starting daemon..."
cd "$ROOT/daemon"
VISIONARK_API_URL="${VISIONARK_API_URL:-http://localhost:8000}" \
VISIONARK_TOKEN="${VISIONARK_TOKEN:-}" \
cargo run &
DAEMON_PID=$!

# Install npm dependencies if node_modules is missing
echo "[2/2] Starting Tauri desktop..."
cd "$ROOT/desktop"
if [ ! -d node_modules ]; then
    echo "    node_modules not found, running npm install..."
    npm install
fi
cargo tauri dev

# Cleanup daemon on exit
trap "kill $DAEMON_PID 2>/dev/null" EXIT

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NATIVE_ROOT="$SCRIPT_DIR/../core/native"

echo "=== VisionArk Native Dev ==="

echo "[1/1] Starting Tauri desktop (daemon is managed by desktop/Tauri command)..."
cd "$NATIVE_ROOT/desktop"
if [[ ! -d node_modules ]]; then
    echo "    node_modules not found, running npm install..."
    npm install
fi
cargo tauri dev

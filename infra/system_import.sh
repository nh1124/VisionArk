#!/usr/bin/env bash
# VisionArk System Import
# Validates integrity, restores PostgreSQL and data/ from an export archive.
#
# Usage: ./infra/system_import.sh [--dry-run] <archive.tar.gz>
#   --dry-run   Validate archive and print restore plan without applying any changes

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

DRY_RUN=false
ARCHIVE=""

usage() {
    echo "Usage: $0 [--dry-run] <archive.tar.gz>"
    echo "  --dry-run   Validate and preview without applying changes"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        -h|--help) usage ;;
        -*)        echo "Unknown option: $1" >&2; exit 1 ;;
        *)         ARCHIVE="$1"; shift ;;
    esac
done

[[ -z "$ARCHIVE" ]] && { echo "ERROR: No archive specified." >&2; usage; }
[[ ! -f "$ARCHIVE" ]]  && { echo "ERROR: Archive not found: $ARCHIVE" >&2; exit 1; }
ARCHIVE="$(realpath "$ARCHIVE")"

# ── Load .env.core (non-overriding) ─────────────────────────────────────────
_load_env() {
    local env_file="$1"
    [[ ! -f "$env_file" ]] && return
    while IFS='=' read -r key rest; do
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        rest="${rest%%#*}"
        rest="${rest%"${rest##*[![:space:]]}"}"
        [[ -z "${!key:-}" ]] && export "$key=$rest"
    done < <(grep -E '^[A-Za-z_][A-Za-z0-9_]*=' "$env_file")
}
if [[ -f "$PROJECT_ROOT/.env.core" ]]; then
    _load_env "$PROJECT_ROOT/.env.core"
else
    echo "ERROR: $PROJECT_ROOT/.env.core not found." >&2
    exit 1
fi

PG_USER="${POSTGRES_USER:-atmos}"
PG_DB="${POSTGRES_DB:-atmos}"
DB_CONTAINER="atmos-db"

# sha256sum vs shasum (macOS)
if command -v sha256sum &>/dev/null; then
    SHA256_CHECK="sha256sum --check"
else
    SHA256_CHECK="shasum -a 256 --check"
fi

echo "========================================"
echo "VISION ARK - System Import"
$DRY_RUN && echo "[DRY RUN MODE — no changes will be applied]"
echo "Archive : $ARCHIVE"
echo "========================================"
echo

# ── Step 1: Extract ──────────────────────────────────────────────────────────
WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT

echo "[1/5] Extracting archive..."
tar -xzf "$ARCHIVE" -C "$WORK_DIR"

BACKUP_DIR=$(find "$WORK_DIR" -maxdepth 1 -mindepth 1 -type d | head -1)
[[ -z "$BACKUP_DIR" ]] && { echo "ERROR: Corrupt archive — no top-level directory." >&2; exit 1; }
echo "      Found: $(basename "$BACKUP_DIR")"

# ── Step 2: Validate manifest ────────────────────────────────────────────────
[[ ! -f "$BACKUP_DIR/manifest.json" ]] && {
    echo "ERROR: manifest.json not found in archive." >&2; exit 1
}

echo "[2/5] Validating manifest.json..."
python3 -c '
import json, sys

with open(sys.argv[1]) as f:
    m = json.load(f)

required = ["schema_version", "db_type", "db_name", "db_user", "files"]
missing = [k for k in required if k not in m]
if missing:
    print(f"ERROR: manifest.json missing fields: {missing}", file=sys.stderr)
    sys.exit(1)

if m["schema_version"] != "1":
    print(f"ERROR: Unsupported schema_version: {m[\"schema_version\"]}", file=sys.stderr)
    sys.exit(1)

if m["db_type"] != "postgresql":
    print(f"ERROR: Unsupported db_type: {m[\"db_type\"]}", file=sys.stderr)
    sys.exit(1)

print(f"      App version : {m.get(\"app_version\", \"unknown\")}")
print(f"      Created at  : {m.get(\"created_at\", \"unknown\")}")
print(f"      DB name     : {m[\"db_name\"]}")
print(f"      Has data    : {m.get(\"has_data_dir\", False)}")
print(f"      Files       : {list(m[\"files\"].keys())}")
' "$BACKUP_DIR/manifest.json"

# ── Step 3: Verify checksums ─────────────────────────────────────────────────
echo "[3/5] Verifying checksums..."
if [[ -f "$BACKUP_DIR/checksums.sha256" ]]; then
    (cd "$BACKUP_DIR" && $SHA256_CHECK checksums.sha256)
    echo "      All checksums OK."
else
    echo "      WARNING: checksums.sha256 not found — skipping verification."
fi

# ── Step 4: Show restore plan ────────────────────────────────────────────────
MANIFEST_DB_NAME=$(python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
print(m['db_name'])
" "$BACKUP_DIR/manifest.json")

HAS_DATA=$(python3 -c "
import json, sys
m = json.load(open(sys.argv[1]))
print('true' if m.get('has_data_dir') else 'false')
" "$BACKUP_DIR/manifest.json")

echo "[4/5] Restore plan:"
echo "      1. Stop containers  : backend, worker"
echo "      2. Terminate active DB connections"
echo "      3. Restore PostgreSQL DB '$MANIFEST_DB_NAME' → container '$DB_CONTAINER'"
if [[ "$HAS_DATA" == "true" ]]; then
    echo "      4. Replace data/ directory from archive"
fi
echo "      5. Restart containers: backend, worker"

if $DRY_RUN; then
    echo
    echo "========================================"
    echo "DRY RUN complete — no changes applied."
    echo "========================================"
    exit 0
fi

# ── Step 5: Apply restore ────────────────────────────────────────────────────
echo
read -rp "[5/5] Apply restore? This will OVERWRITE the current DB and data. (y/n): " confirm
if [[ "${confirm,,}" != "y" ]]; then
    echo "Import cancelled."
    exit 0
fi

if ! docker info &>/dev/null 2>&1; then
    echo "ERROR: Docker is not running." >&2; exit 1
fi
if ! docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
    echo "ERROR: Container '${DB_CONTAINER}' is not running." >&2; exit 1
fi

echo
echo "Stopping backend and worker..."
docker-compose -f "$COMPOSE_FILE" stop backend worker 2>/dev/null || true

echo "Terminating active DB connections..."
docker exec "$DB_CONTAINER" psql -U "$PG_USER" -d postgres -c \
    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$PG_DB' AND pid <> pg_backend_pid();" \
    > /dev/null 2>&1 || true

echo "Restoring database..."
docker exec -i "$DB_CONTAINER" psql -U "$PG_USER" -d "$PG_DB" \
    < "$BACKUP_DIR/db_dump.sql"
echo "  DB restore complete."

if [[ "$HAS_DATA" == "true" ]] && [[ -f "$BACKUP_DIR/data.tar.gz" ]]; then
    echo "Restoring data/..."
    rm -rf "${PROJECT_ROOT:?}/data"
    tar -xzf "$BACKUP_DIR/data.tar.gz" -C "$PROJECT_ROOT"
    echo "  data/ restore complete."
fi

echo "Restarting backend and worker..."
docker-compose -f "$COMPOSE_FILE" start backend worker 2>/dev/null || \
    docker-compose -f "$COMPOSE_FILE" --profile core up -d backend worker

echo
echo "========================================"
echo "Import complete!"
echo "========================================"

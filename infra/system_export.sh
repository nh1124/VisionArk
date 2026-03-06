#!/usr/bin/env bash
# VisionArk System Export
# Dumps PostgreSQL, archives data/, and bundles a manifest + checksums.
#
# Usage: ./infra/system_export.sh [--output-dir DIR] [--no-data]
#   --output-dir DIR   Destination for the .tar.gz archive  (default: ./exports/)
#   --no-data          Skip the data/ directory archive

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"

OUTPUT_DIR="$PROJECT_ROOT/exports"
INCLUDE_DATA=true

usage() {
    echo "Usage: $0 [--output-dir DIR] [--no-data]"
    echo "  --output-dir DIR   Write archive here (default: ./exports/)"
    echo "  --no-data          Skip archiving the data/ directory"
    exit 0
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
        --no-data)    INCLUDE_DATA=false; shift ;;
        -h|--help)    usage ;;
        *)            echo "Unknown option: $1" >&2; exit 1 ;;
    esac
done

# ── Load .env.core (non-overriding) ─────────────────────────────────────────
_load_env() {
    local env_file="$1"
    [[ ! -f "$env_file" ]] && return
    while IFS='=' read -r key rest; do
        [[ "$key" =~ ^[[:space:]]*# ]] && continue
        [[ -z "$key" ]] && continue
        rest="${rest%%#*}"                              # strip inline comment
        rest="${rest%"${rest##*[![:space:]]}"}"         # rtrim whitespace
        [[ -z "${!key:-}" ]] && export "$key=$rest"    # don't overwrite existing
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

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
BACKUP_NAME="visionark_backup_${TIMESTAMP}"

APP_VERSION="unknown"
[[ -f "$PROJECT_ROOT/VERSION" ]] && APP_VERSION=$(cat "$PROJECT_ROOT/VERSION")

# sha256sum vs shasum (macOS)
if command -v sha256sum &>/dev/null; then
    SHA256="sha256sum"
else
    SHA256="shasum -a 256"
fi

echo "========================================"
echo "VISION ARK - System Export"
echo "Archive : ${BACKUP_NAME}.tar.gz"
echo "Output  : $OUTPUT_DIR"
echo "========================================"
echo

# ── Preflight ────────────────────────────────────────────────────────────────
if ! docker info &>/dev/null 2>&1; then
    echo "ERROR: Docker is not running." >&2; exit 1
fi
if ! docker ps --format '{{.Names}}' | grep -q "^${DB_CONTAINER}$"; then
    echo "ERROR: Container '${DB_CONTAINER}' is not running. Start services first." >&2
    exit 1
fi

WORK_DIR=$(mktemp -d)
trap 'rm -rf "$WORK_DIR"' EXIT
STAGE="$WORK_DIR/$BACKUP_NAME"
mkdir -p "$STAGE"

# ── Step 1: PostgreSQL dump ──────────────────────────────────────────────────
echo "[1/4] Dumping PostgreSQL database '$PG_DB'..."
docker exec "$DB_CONTAINER" \
    pg_dump -U "$PG_USER" -d "$PG_DB" --format=plain --clean --if-exists \
    > "$STAGE/db_dump.sql"
echo "      OK  ($(wc -c < "$STAGE/db_dump.sql") bytes)"

# ── Step 2: data/ directory ──────────────────────────────────────────────────
if $INCLUDE_DATA; then
    if [[ -d "$PROJECT_ROOT/data" ]]; then
        echo "[2/4] Archiving data/..."
        tar -czf "$STAGE/data.tar.gz" -C "$PROJECT_ROOT" data
        echo "      OK  ($(wc -c < "$STAGE/data.tar.gz") bytes)"
    else
        echo "[2/4] data/ not found — skipping."
    fi
else
    echo "[2/4] --no-data specified — skipping."
fi

# ── Step 3: SHA-256 checksums ────────────────────────────────────────────────
echo "[3/4] Computing SHA-256 checksums..."
(
    cd "$STAGE"
    $SHA256 db_dump.sql > checksums.sha256
    [[ -f data.tar.gz ]] && $SHA256 data.tar.gz >> checksums.sha256
    cat checksums.sha256
)

# ── Step 4: manifest.json ────────────────────────────────────────────────────
echo "[4/4] Writing manifest.json..."
MANIFEST_STAGE="$STAGE" \
MANIFEST_APP_VERSION="$APP_VERSION" \
MANIFEST_DB_NAME="$PG_DB" \
MANIFEST_DB_USER="$PG_USER" \
MANIFEST_DB_CONTAINER="$DB_CONTAINER" \
python3 -c '
import json, os, datetime

stage        = os.environ["MANIFEST_STAGE"]
app_version  = os.environ.get("MANIFEST_APP_VERSION", "unknown")
db_name      = os.environ["MANIFEST_DB_NAME"]
db_user      = os.environ["MANIFEST_DB_USER"]
db_container = os.environ["MANIFEST_DB_CONTAINER"]

# Parse checksums file
checksums = {}
cs_path = os.path.join(stage, "checksums.sha256")
if os.path.exists(cs_path):
    with open(cs_path) as f:
        for line in f:
            parts = line.strip().split(None, 1)
            if len(parts) == 2:
                checksums[parts[1]] = parts[0]

# Build files dict
files = {}
for fname in ["db_dump.sql", "data.tar.gz"]:
    fpath = os.path.join(stage, fname)
    if os.path.exists(fpath):
        files[fname] = {
            "size_bytes": os.path.getsize(fpath),
            "sha256": checksums.get(fname, ""),
        }

manifest = {
    "schema_version": "1",
    "app_version": app_version,
    "created_at": datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
    "db_type": "postgresql",
    "db_name": db_name,
    "db_user": db_user,
    "db_container": db_container,
    "has_data_dir": "data.tar.gz" in files,
    "files": files,
}
print(json.dumps(manifest, indent=2))
' > "$STAGE/manifest.json"
cat "$STAGE/manifest.json"

# ── Bundle ───────────────────────────────────────────────────────────────────
mkdir -p "$OUTPUT_DIR"
ARCHIVE="$OUTPUT_DIR/${BACKUP_NAME}.tar.gz"
echo
echo "Bundling archive..."
tar -czf "$ARCHIVE" -C "$WORK_DIR" "$BACKUP_NAME"

echo
echo "========================================"
echo "Export complete!"
echo "Archive : $ARCHIVE"
echo "Size    : $(du -h "$ARCHIVE" | cut -f1)"
echo "========================================"

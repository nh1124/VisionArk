#!/usr/bin/env bash
set -euo pipefail

# Show rows from service_registry.
#
# Usage:
#   bash infra/show_service_registry.sh
#   bash infra/show_service_registry.sh /path/to/.env.core
#   bash infra/show_service_registry.sh /path/to/.env.core lbs
#
# Optional env override:
#   DB_CONTAINER=custom-db-container bash infra/show_service_registry.sh

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${1:-${REPO_ROOT}/.env.core}"
SERVICE_NAME_FILTER="${2:-}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[ERROR] env file not found: ${ENV_FILE}" >&2
  exit 1
fi

get_env() {
  local key="$1"
  grep -E "^${key}=" "${ENV_FILE}" | tail -n1 | cut -d'=' -f2- | tr -d '\r'
}

POSTGRES_USER="$(get_env POSTGRES_USER)"; POSTGRES_USER="${POSTGRES_USER:-atmos}"
POSTGRES_PASSWORD="$(get_env POSTGRES_PASSWORD)"; POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-atmos_secret}"
POSTGRES_DB="$(get_env POSTGRES_DB)"; POSTGRES_DB="${POSTGRES_DB:-atmos}"
DB_CONTAINER="${DB_CONTAINER:-atmos-db}"

echo "[INFO] DB container: ${DB_CONTAINER}"
echo "[INFO] DB: ${POSTGRES_DB} (user=${POSTGRES_USER})"

if [[ -n "${SERVICE_NAME_FILTER}" ]]; then
  SQL="
SELECT id, user_id, service_name, base_url, is_active, updated_at
FROM service_registry
WHERE service_name = '${SERVICE_NAME_FILTER}'
ORDER BY updated_at DESC;
"
else
  SQL="
SELECT id, user_id, service_name, base_url, is_active, updated_at
FROM service_registry
ORDER BY service_name, updated_at DESC;
"
fi

docker exec -e PGPASSWORD="${POSTGRES_PASSWORD}" "${DB_CONTAINER}" \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 -c "${SQL}"

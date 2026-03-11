#!/usr/bin/env bash
set -euo pipefail

# Sync service_registry.base_url for service_name='lbs' from .env.core
# Usage:
#   bash infra/sync_lbs_base_url_from_env.sh
#   bash infra/sync_lbs_base_url_from_env.sh /path/to/.env.core

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${1:-${REPO_ROOT}/.env.core}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[ERROR] env file not found: ${ENV_FILE}" >&2
  exit 1
fi

get_env() {
  local key="$1"
  local val
  val="$(grep -E "^${key}=" "${ENV_FILE}" | tail -n1 | cut -d'=' -f2- | tr -d '\r')"
  echo "${val}"
}

POSTGRES_USER="$(get_env POSTGRES_USER)"
POSTGRES_PASSWORD="$(get_env POSTGRES_PASSWORD)"
POSTGRES_DB="$(get_env POSTGRES_DB)"
LBS_SERVICE_URL="$(get_env LBS_SERVICE_URL)"

POSTGRES_USER="${POSTGRES_USER:-atmos}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-atmos_secret}"
POSTGRES_DB="${POSTGRES_DB:-atmos}"

if [[ -z "${LBS_SERVICE_URL}" ]]; then
  echo "[ERROR] LBS_SERVICE_URL is empty in ${ENV_FILE}" >&2
  exit 1
fi

echo "[INFO] Applying LBS base_url from ${ENV_FILE}"
echo "[INFO] target URL: ${LBS_SERVICE_URL}"
echo "[INFO] target DB : ${POSTGRES_DB} (user=${POSTGRES_USER})"

docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" atmos-db \
  psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" \
  -v ON_ERROR_STOP=1 -v lbs_url="${LBS_SERVICE_URL}" <<'SQL'
BEGIN;
UPDATE service_registry
SET base_url = :'lbs_url',
    updated_at = NOW()
WHERE service_name = 'lbs';

SELECT COUNT(*) AS lbs_rows, MIN(base_url) AS current_lbs_base_url
FROM service_registry
WHERE service_name = 'lbs';
COMMIT;
SQL

echo "[INFO] Done."

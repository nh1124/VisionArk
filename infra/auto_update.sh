#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
COMPOSE_FILE="$SCRIPT_DIR/docker-compose.yml"
LOCK_FILE="/tmp/visionark-auto-update.lock"

MODE="${1:-watch}"
CHECK_INTERVAL_SECONDS="${CHECK_INTERVAL_SECONDS:-60}"
TARGET_BRANCH="${TARGET_BRANCH:-}"
DEPLOY_PROFILES="${DEPLOY_PROFILES:-core ui}"
ALLOW_DIRTY="${ALLOW_DIRTY:-0}"
RESTART_AFTER_PULL="${RESTART_AFTER_PULL:-1}"
ENV_FILE="${ENV_FILE:-$PROJECT_ROOT/.env.core}"

timestamp() {
    date +"%Y-%m-%d %H:%M:%S"
}

log() {
    echo "[$(timestamp)] $*"
}

require_commands() {
    local required=(git awk sed)
    for cmd in "${required[@]}"; do
        if ! command -v "$cmd" >/dev/null 2>&1; then
            log "ERROR: Required command not found: $cmd"
            exit 1
        fi
    done

    if command -v docker-compose >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker-compose"
    elif docker compose version >/dev/null 2>&1; then
        DOCKER_COMPOSE="docker compose"
    else
        log "ERROR: Docker Compose not found."
        exit 1
    fi
}

resolve_branch() {
    if [[ -n "$TARGET_BRANCH" ]]; then
        return
    fi

    TARGET_BRANCH="$(git -C "$PROJECT_ROOT" rev-parse --abbrev-ref HEAD)"
    if [[ "$TARGET_BRANCH" == "HEAD" ]]; then
        log "ERROR: Detached HEAD detected. Set TARGET_BRANCH explicitly."
        exit 1
    fi
}

ensure_clean_worktree() {
    if [[ "$ALLOW_DIRTY" == "1" ]]; then
        return
    fi

    if [[ -n "$(git -C "$PROJECT_ROOT" status --porcelain)" ]]; then
        log "WARN: Working tree is dirty. Skipping update (set ALLOW_DIRTY=1 to override)."
        return 1
    fi
}

compose_up() {
    local profile_args=()
    local profile
    for profile in $DEPLOY_PROFILES; do
        profile_args+=(--profile "$profile")
    done

    if [[ ! -f "$ENV_FILE" ]]; then
        log "ERROR: ENV file not found: $ENV_FILE"
        exit 1
    fi

    log "Running Docker Compose deploy for profiles: $DEPLOY_PROFILES"
    (
        cd "$PROJECT_ROOT"
        CORE_ENV_FILE="../.env.core" EDGE_ENV_FILE="../.env.edge" \
        $DOCKER_COMPOSE --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "${profile_args[@]}" up -d --build
    )
}

update_once() {
    local local_commit remote_commit

    local_commit="$(git -C "$PROJECT_ROOT" rev-parse HEAD)"
    remote_commit="$(git -C "$PROJECT_ROOT" ls-remote --heads origin "$TARGET_BRANCH" | awk '{print $1}')"

    if [[ -z "$remote_commit" ]]; then
        log "ERROR: Could not resolve remote commit for branch origin/$TARGET_BRANCH"
        return 1
    fi

    if [[ "$local_commit" == "$remote_commit" ]]; then
        log "No changes on origin/$TARGET_BRANCH (local=$local_commit)"
        return 0
    fi

    log "Update detected on origin/$TARGET_BRANCH (local=$local_commit, remote=$remote_commit)"

    if ! ensure_clean_worktree; then
        return 0
    fi

    (
        cd "$PROJECT_ROOT"
        git fetch origin "$TARGET_BRANCH"
        git pull --ff-only origin "$TARGET_BRANCH"
    )

    if [[ "$RESTART_AFTER_PULL" == "1" ]]; then
        compose_up
    else
        log "Skipping Docker restart (RESTART_AFTER_PULL=$RESTART_AFTER_PULL)"
    fi
}

watch_loop() {
    log "Starting watch mode (interval=${CHECK_INTERVAL_SECONDS}s, branch=${TARGET_BRANCH}, profiles=${DEPLOY_PROFILES})"
    while true; do
        update_once || true
        sleep "$CHECK_INTERVAL_SECONDS"
    done
}

main() {
    require_commands
    resolve_branch

    if command -v flock >/dev/null 2>&1; then
        exec 200>"$LOCK_FILE"
        if ! flock -n 200; then
            log "Another auto_update.sh process is running. Exiting."
            exit 0
        fi
    else
        log "WARN: flock not found. Locking is disabled."
    fi

    case "$MODE" in
        once)
            log "Running one-shot update check"
            update_once
            ;;
        watch)
            watch_loop
            ;;
        *)
            log "ERROR: Unknown mode '$MODE'. Use 'once' or 'watch'."
            exit 1
            ;;
    esac
}

main "$@"

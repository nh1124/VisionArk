# VisionArk

VisionArk is an experimental AI-assisted workspace platform built around the `orchestration2` engine.

- Backend: FastAPI + domain modules
- Frontend: Next.js
- Native: Rust/Tauri workspace under `core/native`
- Runtime: PostgreSQL + Redis + worker + optional Cloudflare tunnel

> Status: active development, not production-ready.

## Current Architecture (Code-Verified)

Core backend domains live in `core/backend/domains/`:

- `orchestration2`: graph-driven agent execution core (roles/tools/registries/bootstrap)
- `workspace`: project/workspace files, context, notifications
- `long_running`: long-running job handlers and executor
- `monitoring`: collectors, detectors, notifiers, monitoring schedules
- `native`: native runtime bridge service
- `automation`, `identity`, `knowledge`

API entrypoints are under `core/backend/api/` (for example: `agents`, `definitions`, `monitoring`, `native`, `long_running_jobs`).

## Repository Layout

```text
VisionArk/
  core/
    backend/
    frontend/
    native/
  infra/
    docker-compose.yml
    start_*.sh / start_*.bat
    initialize_system.*
    system_export.* / system_import.*
  integrations/
  assets/
  data/
  docs/
  va_sdk/
```

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ (local backend development)
- Node.js 18+ (local frontend/native development)
- Rust/Cargo + Tauri dependencies (native development)
- At least one LLM provider key in environment (default template uses Gemini)

## Environment Files

This project uses layered env files.

1. Create env files from templates:

```bash
cp .env.core.example .env.core
cp .env.edge.example .env.edge
```

2. Fill required values:
- `.env.core`: `GEMINI_API_KEY`, `JWT_SECRET_KEY`, `ATMOS_SERVICE_KEY` (plus DB overrides if needed)
- `.env.edge`: `TUNNEL_TOKEN` (only if using tunnel)

## Docker Compose Profiles

Defined in `infra/docker-compose.yml`:

- `core`: `db`, `backend`, `worker`, `redis`
- `ui`: `frontend`
- `edge`: `tunnel`
- `all`: all services

Examples:

```bash
docker compose --env-file .env.core -f infra/docker-compose.yml --profile core --profile ui up
```

```bash
docker compose --env-file .env.edge -f infra/docker-compose.yml --profile edge up tunnel
```

## Startup Scripts

Windows:

```bat
.\infra\start_backend.bat
.\infra\start_frontend.bat
.\infra\start_tunnel.bat
.\infra\start_native.bat
.\infra\start_all.bat
```

Linux/macOS:

```bash
./infra/start_backend.sh
./infra/start_frontend.sh
./infra/start_tunnel.sh
./infra/start_native.sh
./infra/start_all.sh
```

## Native Development

Native workspace is under `core/native/` and includes:

- `daemon/` (Rust)
- `bridge/` + `bridge-rs/`
- `desktop/` (Tauri app)

Run via:
- `infra/start_native.sh` (Linux/macOS)
- `infra/start_native.bat` (Windows)

## Access

- Frontend: <http://localhost:3000>
- API docs: <http://localhost:8000/docs>
- Health check: <http://localhost:8000/health>

## Operational Scripts

- Initialize (destructive): `infra/initialize_system.sh` / `.bat`
- Export backup: `infra/system_export.sh` / `.bat`
- Import backup: `infra/system_import.sh` / `.bat`
- Auto-update helper: `infra/auto_update.sh`

## Documentation

- Main docs index: `docs/README.md`
- Core architecture docs: `docs/core/`
- ADRs: `docs/decisions/`

## License

Apache License 2.0. See `LICENSE`.
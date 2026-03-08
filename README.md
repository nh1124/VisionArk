# VisionArk

> Experimental personal OS for AI-assisted project and task orchestration.
> This repository is not production-ready.

VisionArk is an AI-powered personal task management system built on a Project/Node architecture.
It combines LBS (Load Balancing System) workload management with multi-agent orchestration.

## Core Features

- Project/Node agent architecture (Project Node + Member Nodes)
- Agent-to-agent coordination (`ask_node`) with bounded recursion
- Async task execution with worker queue
- Artifacts and workspace file management
- LBS scheduling and workload balancing
- Knowledge retrieval and memory ingestion
- Optional Cloudflare tunnel for edge exposure
- Optional native desktop dev flow

## Tech Stack

- Frontend: Next.js, React, Tailwind CSS
- Backend: FastAPI, SQLAlchemy (async), Pydantic
- Queue: Redis
- Database: PostgreSQL (Docker profile)
- Deployment: Docker Compose profiles

## Prerequisites

- Docker + Docker Compose
- Python 3.11+ (for local backend development only)
- Node.js 18+ (for local frontend/native development only)
- Gemini API key (or your configured provider)

## Environment Layering

VisionArk no longer uses `.env`.
Use layered files instead:

- `.env.core`: shared vars for `db/backend/worker/frontend`
- `.env.edge`: vars for `tunnel` only
- Optional overlays: `.env.shared`, `.env.local`

Setup:

```bash
cp .env.core.example .env.core
cp .env.edge.example .env.edge
```

Required minimum:

- In `.env.core`: `GEMINI_API_KEY`, `JWT_SECRET_KEY`, `ATMOS_SERVICE_KEY`
- In `.env.edge`: `TUNNEL_TOKEN`

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

## Role-Based Startup Scripts

### Windows

```bat
.\infra\start_backend.bat
.\infra\start_frontend.bat
.\infra\start_tunnel.bat
.\infra\start_native.bat
.\infra\start_all.bat
```

### Linux/macOS

```bash
./infra/start_backend.sh
./infra/start_frontend.sh
./infra/start_tunnel.sh
./infra/start_native.sh
./infra/start_all.sh
```

## Access

- UI: <http://localhost:3000>
- API Docs: <http://localhost:8000/docs>

## Cloudflare Tunnel Safety

Do **not** use the same `TUNNEL_TOKEN` simultaneously across multiple environments.
Use separate tokens for local/dev/staging validation.

## Useful Operations

### Initialize system (destructive)

Removes containers/volumes and clears local data.

- `infra/initialize_system.sh`
- `infra/initialize_system.bat`

### Export / Import backup

- Export: `infra/system_export.sh` or `.bat`
- Import: `infra/system_import.sh` or `.bat`

These scripts now load `.env.core`.

### Auto update on Git changes (Linux/macOS server)

Use `infra/auto_update.sh` to detect remote branch updates and auto-deploy.

One-shot check:

```bash
./infra/auto_update.sh once
```

Watch mode (every 60s by default):

```bash
./infra/auto_update.sh watch
```

Useful env vars:

- `TARGET_BRANCH` (default: current branch)
- `CHECK_INTERVAL_SECONDS` (default: `60`)
- `DEPLOY_PROFILES` (default: `core ui`)
- `RESTART_AFTER_PULL` (`1` to run compose up after pull, default `1`)
- `ALLOW_DIRTY` (`0` by default; set `1` to ignore dirty worktree)

Example:

```bash
TARGET_BRANCH=main CHECK_INTERVAL_SECONDS=30 DEPLOY_PROFILES="core ui edge" ./infra/auto_update.sh watch
```

## Native Development

Native scripts moved to `infra/start_native.sh` and `infra/start_native.bat`.
Legacy `core/native/scripts/dev.*` has been removed.

## Project Structure

```text
VisionArk/
  core/
    backend/
    frontend/
    native/
  infra/
    docker-compose.yml
    start_backend.*
    start_frontend.*
    start_tunnel.*
    start_native.*
    start_all.*
  integrations/
  docs/
  assets/
  data/
```

## License

Apache License 2.0. See `LICENSE`.

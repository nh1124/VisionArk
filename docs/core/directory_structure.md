# Project Directory Structure

## Overview
VisionArk backend follows a domain-oriented architecture centered on `core/backend/domains/` and the `orchestration2` execution engine.

- Domain logic is grouped by business capability under `domains/`.
- API entry points live under `api/` and `app/`.
- Technical integrations (LLM providers, queue) are under `infrastructure/`.
- Cross-cutting helpers and DB primitives are under `shared/`.

## Root Directory (`VisionArk/`)
- `core/`: Main source tree.
  - `backend/`: FastAPI backend and agent runtime.
  - `frontend/`: Web UI.
  - `native/`: Native runtime and desktop app workspace (bridge, daemon, Tauri desktop).
- `docs/`: Documentation and ADRs.

## Backend Structure (`core/backend/`)

### 1. App Layer (`app/`)
- `main.py`: FastAPI bootstrap and router wiring.
- `worker.py`: Background worker bootstrap.
- `config.py`: Runtime settings and environment handling.

### 2. API Layer (`api/`)
Representative endpoint groups:
- `agents.py`, `commands.py`, `decomposer.py`
- `definitions.py`, `approvals.py`, `automation.py`
- `long_running_jobs.py`, `monitoring.py`, `native.py`
- `files.py`, `notes.py`, `notifications.py`, `workspace.py`

### 3. Domain Layer (`domains/`)
Current domain packages:
- `automation/`: Scheduling and command parsing (AES scheduler/dispatcher and command library).
- `identity/`: Identity and user-related domain logic.
- `knowledge/`: Knowledge and retrieval-related domain logic.
- `long_running/`: Long-running job models, handlers, executor, and service.
- `monitoring/`: Collectors, detectors, notifiers, monitoring service/scheduling.
- `native/`: Native runtime bridge (`run_service.py`).
- `orchestration2/`: Primary orchestration engine and runtime assembly.
- `workspace/`: Workspace context, files, and notification services.

> Note: `domains/orchestration/` is not part of the current structure; `domains/orchestration2/` is the active orchestration domain.

### 4. Infrastructure Layer (`infrastructure/`)
- `llm/`: Provider adapters and model routing (OpenAI/Anthropic/Orchestration provider integration).
- `queue/`: Queue manager and background execution integration.

### 5. Shared Layer (`shared/`)
- `database.py`: DB models/session utilities.
- `seed.py`: Seed and initialization helpers.
- `paths.py`: Path conventions and filesystem helpers.
- `security.py`, `jwt.py`, `encryption.py`: Security/auth primitives.
- `logger.py`, `service_helpers.py`: Shared runtime helpers.

## Orchestration2 Highlights (`domains/orchestration2/`)
- `engine/`: Core execution abstractions (interfaces, models, orchestrator, registries, stores).
- `engine_runtime/`: LLM runtime engines.
- `bootstrap/`: Definition import/refresh/validation and project engine builder.
- `config/`: Default graph/tool/skill catalogs.
- `roles/` and `tools/library/`: Role policies and standard tool implementations.
- `integrations/`: Tool/skill import and reflection services.

## Maintenance Guidance
- Keep this document aligned with actual directories under `core/backend/`.
- When adding or moving a domain package, update this file in the same PR.

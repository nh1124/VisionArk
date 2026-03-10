# VisionArk System Design

## Purpose
VisionArk is a multi-domain assistant platform that combines:
- conversational orchestration,
- project and workspace operations,
- long-running execution,
- monitoring/notification workflows,
- integration with external and native tool surfaces.

This document summarizes the current backend architecture after the orchestration2-centered refactor.

## System Scope
Primary backend scope is `core/backend/`:
- API and worker entry points (`app/`, `api/`)
- Domain modules (`domains/`)
- Infra adapters (`infrastructure/`)
- Shared runtime/data utilities (`shared/`)

## Architectural Principles

### 1. Domain-Oriented Separation
Business capabilities are isolated under `domains/*` (for example `workspace`, `monitoring`, `long_running`, `native`).

### 2. Orchestration2 as Execution Core
`domains/orchestration2/` is the runtime center for:
- graph-driven orchestration,
- role and tool registries,
- approvals/delegation flow,
- skill/tool composition.

### 3. Registry and Definition Management
Skill/tool definitions are managed through orchestrated loaders and registry services (not legacy filesystem-only sync).

### 4. Replaceable Infrastructure
LLM providers and queue execution are abstracted in `infrastructure/` so providers can be swapped with limited domain impact.

## Runtime Topology

### API and Worker
- `app/main.py`: Starts FastAPI, wires routers, and bootstraps runtime dependencies.
- `app/worker.py`: Handles asynchronous/background execution paths.

### Domain Composition
Current domains:
- `automation`
- `identity`
- `knowledge`
- `long_running`
- `monitoring`
- `native`
- `orchestration2`
- `workspace`

### Orchestration2 Internal Composition
Key modules:
- `engine/`: interfaces, models, orchestration flow, and stores
- `engine_runtime/`: model runtime adapters
- `bootstrap/`: project engine building and definition refresh/import/validation
- `roles/`: agent role behavior
- `tools/library/`: built-in tool surface
- `config/`: default graph/tool/skill catalogs

## Integration Surfaces

### LLM Integration Profile
`infrastructure/llm/` provides:
- provider registry,
- model catalog/router,
- provider adapters.

### Queue Integration Profile
`infrastructure/queue/` provides queue and job execution coordination.

### Native and External Integration Profile
- Native runtime bridge is in `domains/native/run_service.py`.
- Integration-aware tool/skill reflection/import is in `domains/orchestration2/integrations/`.

## Data and Shared Services
`shared/` contains shared primitives used across domains:
- database/session/model helpers,
- auth/security/token/encryption utilities,
- path and seed utilities,
- shared logging/service helpers.

## Request-to-Execution Flow (High Level)
1. Client sends a request to FastAPI endpoints under `api/`.
2. API layer dispatches work to domain services.
3. For agentic execution, orchestration routes through `orchestration2`.
4. Runtime uses configured tools/skills and LLM providers.
5. Long-running or scheduled work is delegated to worker/queue paths.
6. Monitoring and notification domains publish user-visible outcomes.

## Non-Goals
- This document does not define feature-level API contracts.
- This document does not replace ADRs for major decisions.

## Related Docs
- [Directory Structure](./directory_structure.md)
- [Orchestration2 Engine](./orchestration2_engine.md)
- [Orchestration2 Delegation v1](./orchestration2_delegation_v1.md)
- [LLM Provider System](./llm_provider_system.md)
- [External Integration](./external_integration.md)
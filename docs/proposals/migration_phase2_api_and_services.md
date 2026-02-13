# Migration Phase 2: API & Services

**Goal**: Update the API layer to interact with the new `ProjectAgent`/`ProjectSkill` models and remove all references to `node_id`, ensuring the API contract is fully decoupled from the legacy Node architecture.

**Reference**: `docs/reports/node_to_orchestration2_residue_report.md` (Section 2 - Proposal 2 & 5)

## Prerequisites
- Phase 1 (Database Changes) must be applied (or applied concurrently).

## Plan

### 1. Update `core/backend/api/agents.py`

#### A. Project Creation (`create_project` / `create_project_from_prompt`)
- **Legacy**: Created a `Project` and then a `Node` (Main Node).
- **New**: Create a `Project` and a `ProjectAgent` (Main Assistant Profile).
- **Response**: Remove `node_id` from the returned JSON. Return `project_id` and potentially `agent_config` if needed.

#### B. Prompt Management (`get_project_system_prompt`, etc.)
- **Legacy**: Queried `Node` table by `node_id` or `project.main_node`.
- **New**: Query `ProjectAgent` table by `project_id` (filtering by role='main' or similar).

### 2. Update `core/backend/api/skills.py`
- **Legacy**: Endpoints like `/api/skills/node/{node_id}`.
- **New**: Rename/Refactor to `/api/skills/project/{project_id}`.
- Logic: Attach skills to the `Project` (via `ProjectSkill`) instead of a `Node`.

### 3. Update `core/backend/api/rag.py`
- **Legacy**: Used `select(Node.id)...` to verify project/node existence.
- **New**: Use `select(Project.id).where(Project.id == project_id)` directly.
- Ensure dependency `ensure_project_access` is standardized.

### 4. Search & Destroy
- Grep for `node_id` in all `core/backend/api/` files.
- Replace with `project_id` or `agent_id` where appropriate.

## Verification
- Unit tests for API endpoints should pass.
- Manual verification via Swagger UI (if available) to ensure `node_id` is gone and basic CRUD operations work.

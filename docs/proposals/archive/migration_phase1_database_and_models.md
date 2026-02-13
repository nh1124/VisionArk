# Migration Phase 1: Database & Models

**Goal**: Transition the database schema from a Node-centric model (Legacy) to a Project+Agent-centric model (Orchestration2), effectively removing the `Node` concept from the persistence layer.

**Reference**: `docs/reports/node_to_orchestration2_residue_report.md` (Section 2 - Proposal 1)

## Prerequisites
- The database is considered **reset-able**. We do not need to write complex Alembic migrations to preserve data. We can modify the model definitions directly.
- The goal is **maintainability** and **engine independence**.

## Plan

### 1. Modify `core/backend/shared/database.py`

#### A. Remove Legacy Models
Remove or comment out the following classes/tables:
- `NodeType` (Enum)
- `Node` (Table)
- `NodeSkill` (Table)

#### B. Define New Models
Introduce new models to represent the state required by Orchestration2:

1.  **`ProjectAgent`** (Replaces the concept of a "Main Node" or "System Node")
    - `id`: UUID (PK)
    - `project_id`: UUID (FK to `Project`)
    - `name`: String (e.g., "Main Assistant")
    - `role`: String (e.g., "main", "responder") - *Align with Orchestration2 roles*
    - `system_prompt`: Text (The prompt previously stored on the Node)
    - `created_at`, `updated_at`

2.  **`ProjectSkill`** (Replaces `NodeSkill`)
    - `id`: UUID (PK)
    - `project_id`: UUID (FK to `Project`)
    - `skill_name`: String (or FK if skills are normalized, but strictly Project-scoped now)
    - `config`: JSON (Any skill-specific configuration)
    - *Note: If skills were attached to specific agents, consider `agent_id` FK too, but `project_id` might be sufficient if skills are shared in the project context.*


#### C. Update `Project` Model
- Remove `nodes` relationship.
- Add `agents` relationship (to `ProjectAgent`).
- Add `skills` relationship (to `ProjectSkill`).

## Verification
- Run `python -m core.backend.shared.database` (or equivalent) to ensure models load without error.
- Generate a fresh DB schema (using existing init scripts) and verify tables are created correctly.
- Verify no other files fail to import `database.py` due to missing `Node` class (this will likely break other files, which is expected and will be fixed in subsequent phases, but for *this* phase, keeping stub classes might be necessary if we want to avoid immediate crash, OR we accept breakage until Phase 2/3).
    - *Strategy*: If possible, perform Phase 1, 2, and 3 changes in close succession or monolithic PR. if treating as separate tasks, assume the codebase will be temporarily broken until Phase 3 is done.

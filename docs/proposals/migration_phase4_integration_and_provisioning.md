# Migration Phase 4: Integration & Provisioning

**Goal**: Decouple external integrations (e.g., LINE) from internal database schemas by introducing a `ProjectProvisioningService`.

**Reference**: `docs/reports/node_to_orchestration2_residue_report.md` (Section 2 - Proposal 4)

## Prerequisites
- Core DB models (Phase 1) must be defined.

## Plan

### 1. Create `ProjectProvisioningService`
- **Location**: `core/backend/domains/provisioning/service.py` (New Domain)
- **Responsibilities**:
    - `create_project_workspace(user_id, name, ...)`
    - `initialize_project_profile(project_id, ...)`: Sets up the default `ProjectAgent` and `system_prompt`.
    - `bind_external_identity(project_id, provider, external_id)`: Handles mapping external IDs to the project.

### 2. Update Integrations (e.g., LINE)
- **Target**: `integrations/line/api.py` (and similar).
- **Action**: Remove code that does `Project(...)` or `Node(...)` instantiation directly.
- **Action**: Inject or import `ProjectProvisioningService`.
- **Action**: Call `provisioning_service.create_project_workspace(...)` to setup new users/chats.

## Verification
- If possible, trigger the LINE webhook (or mock it) to verify that a new user interaction correctly creates a Project and an Agent without using the old `Node` logic.

# Migration Phase 3: Worker & Queue

**Goal**: Unify the background execution path to solely support `Orchestration2` runs, removing legacy `Node` execution paths and the `queue` logic that supported them.

**Reference**: `docs/reports/node_to_orchestration2_residue_report.md` (Section 2 - Proposal 3)

## Prerequisites
- Phase 1 & 2 should be in progress or understood, as the Worker depends on the DB models.

## Plan

### 1. Update `core/backend/shared/database.py` (Enum)
- **Action**: Update `TaskType` enum.
- **Remove**: `NODE_EXECUTION`, `AI_ROUTING` (if legacy).
- **Keep/Add**: `ORCHESTRATION_RUN` (or `SYSTEM_TASK` / `USER_MESSAGE` if that's the new taxonomy). Be sure it aligns with `Orchestration2`.

### 2. Update `core/backend/infrastructure/queue/manager.py`
- **Action**: Remove `enqueue_node_task` method.
- **Action**: Ensure `enqueue_orchestration_run` (or equivalent) is the primary entry point.
- **Data**: Ensure the payload uses `project_id` / `run_id` / `agent_id` instead of `node_id`.

### 3. Update `core/backend/app/worker.py`
- **Action**: Remove the branching logic that handles `TaskType.NODE_EXECUTION`.
- **Action**: Remove `NodeFactory`, `SchedulerNode`, `RouterNode` imports and usages.
- **Action**: Ensure `_handle_user_message` or `_run_orchestration2` is the sole logic path.
- **Context**: Verify `context` dictionary keys no longer expect `node_id`.

### 4. Cleanup `core/backend/domains/orchestration` (Legacy)
- Once the worker no longer imports from the legacy `domains/orchestration` package, delete the folder (or move to `_legacy/` if uncertain, but strict deletions are requested).

## Verification
- Start `uvicorn` and `worker`.
- Send a chat message via the (updated) API.
- Verify the Worker picks it up as an orchestration run and executes it without looking for `nodes`.

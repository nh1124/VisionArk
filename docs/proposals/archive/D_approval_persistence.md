# Proposal D: Persist Approval/Delegation State

## Status
Proposed

## Priority
P1

## Objectives
Strengthen work continuity and resilience against interruptions.

## Details
-   Migrate pending approval/delegation state management to DB.
-   Enable `resume(run_id)` to be feasible even after process restart.

## Expected Benefits
-   Robust foundation for long-running tasks and human-in-the-loop workflows.

## Scope & Risks
-   **Scope**: Large. Changes to `store/sqlalchemy_store.py`, DB schema, and resume path.
-   **Risk**: Migration and consistency verification costs.

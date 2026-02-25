# Proposal E: Expand Orchestration2 Scope to Peripheral APIs

## Status
Proposed

## Priority
P1

## Objectives
Unify implementation and improve observability.

## Details
-   Execute `create-from-prompt` and `decompose` using lightweight graphs.
-   Leave common `run_id` / event logs.

## Expected Benefits
-   Easier lateral deployment of quality improvement measures and comparative analysis.

## Scope & Risks
-   **Scope**: Medium. Changes to `api/agents.py`, `api/decomposer.py`, etc.
-   **Risk**: Differences in existing response specifications.

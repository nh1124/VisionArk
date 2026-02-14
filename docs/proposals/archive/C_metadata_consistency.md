# Proposal C: Metadata Key Consistency

## Status
Proposed

## Priority
P0

## Objectives
Ensure custom prompts are reliably reflected.

## Details
-   Align `ProjectRole` reference key to `agent_profile` (or support both).
-   Address inconsistency between `engine_setup` (sets `agent_profile`) and `ProjectRole` (reads `node_profile`).

## Expected Benefits
-   Agent personality and operational rules are reflected in execution, reducing quality variance.

## Scope & Risks
-   **Scope**: Small. Modify `roles/project_role.py` (and potentially `engine_setup.py`).
-   **Risk**: Low.

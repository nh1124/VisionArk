# Proposal B: Introduce Skill Constraints

## Status
Proposed

## Priority
P0

## Objectives
Concentrate reasoning and improve safety by limiting the set of available tools.

## Details
-   Define `SkillDef` for each major use case (investigation, document creation, file manipulation, operation).
-   Switch active skills per graph step, exposing only necessary tools.

## Expected Benefits
-   Reduction of tool abuse.
-   Token saving.
-   Easier isolation of causes when failures occur.

## Scope & Risks
-   **Scope**: Medium to Large. Requires adding skill implementations, setting `skills` during agent registration, and operational design.
-   **Risk**: Early failures due to lack of tools if not properly configured.

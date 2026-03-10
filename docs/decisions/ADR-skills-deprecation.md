# ADR: Deprecation of Legacy Skill Components

- **Date**: 2026-02-18 (Updated: 2026-02-20)
- **Status**: Accepted
- **Context**:
  - [skills_refactor_assessment_20260217.md](../proposals/archive/skills_refactor_assessment_20260217.md)
  - [Skill_refactoring.md](../proposals/archive/Skill_refactoring.md)

## Decision

Deprecate and remove the following legacy skill components in favor of the `orchestration2` engine's `SkillDef` and `SkillRegistry`.

| Removed Component | Reason |
|---|---|
| `domains/automation/skill_service.py` | Unused (zero imports) and not connected to orchestration2 execution. |
| `domains/automation/skills/registry.py` | Legacy filesystem `SKILL.md` to DB sync path replaced by current UI/API-based management. |
| `domains/automation/skills/__init__.py` (`init_skills()`) | Entry point for the removed legacy registry sync. |

## Rationale

1. **Single source of truth**: orchestration2 defines skill behavior through `SkillDef` and `SkillRegistry`. Legacy `SkillService` used a model not wired to execution.
2. **No functional loss**: `SkillService` was dead code and can be removed safely.
3. **Frontend alignment**: skills UI now uses existing `/api/skills/project/{project_id}` API paths.

## Consequences

- Skills are managed via the Skills UI and `/api/skills` API endpoints.
- Filesystem-based sync from legacy `domains/automation/skills/` is removed.
- DB-backed skill loading remains active through orchestration2 prompt context loading.

## Phase 1 Notes (2026-02-20)

Based on [Skill_refactoring.md](../proposals/archive/Skill_refactoring.md), Phase 1 consolidated runtime skill handling into orchestration2.

- `/api/skills` remains the CRUD API for persisted skill data.
- `prompt_context_loader` and engine assembly load DB skills into runtime prompt context.
- Frontend skills pages were aligned to existing backend endpoints.
- Integration-side `SKILL.md` runtime use was narrowed to relevant tool policies.

## Phase D Notes (2026-03-02): DB-Centric Definitions

Reference: [tool_skill_db_refactor_report.md](../proposals/archive/tool_skill_db_refactor_report.md)

Major outcomes:
- `tool_registry` and `skill_registry` became the primary runtime definition source.
- Definition refresh services upsert core/integration definitions into DB.
- Engine builder now resolves active dynamic skills/tools from DB with fallback strategy.
- `/api/definitions` endpoints were added for refresh and inspection flows.

## Phase E Notes (2026-03-02): User Uploaded Tool/Skill Flows

Major outcomes:
- User custom tools are stored under user-scoped paths and validated before registration.
- Import and activation flows are managed through `/api/definitions` endpoints.
- Runtime loads active user custom tools through integration-aware adapters.
- Hot reload remains outside this phase scope.
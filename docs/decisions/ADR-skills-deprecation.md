# ADR: Deprecation of Legacy Skill Components

- **Date**: 2026-02-18
- **Status**: Accepted
- **Context**: [skills_refactor_assessment_20260217.md](../proposals/skills_refactor_assessment_20260217.md)

## Decision

Deprecate and remove the following legacy skill components in favor of the `orchestration2` engine's `SkillDef` / `SkillRegistry`:

| Removed Component | Reason |
|---|---|
| `domains/automation/skill_service.py` | Unused — zero imports across the entire codebase. Intent/priority/conflict/tool_policy logic is not connected to orchestration2 execution. |
| `domains/automation/skills/registry.py` | Filesystem-based `SKILL.md → DB` sync with incorrect search paths. Replaced by UI/API skill management. |
| `domains/automation/skills/__init__.py` (`init_skills()`) | Entry point for the removed registry sync. Called from `main.py` and `worker.py` lifespan hooks. |

## Rationale

1. **Single source of truth**: `orchestration2` defines skill behavior via `SkillDef(name, description, tools, request_approval)` and `SkillRegistry`. The legacy `SkillService` used a different model (`metadata_payload` with `intent/priority/conflicts/tool_policy`) that was never connected to the execution path.

2. **No functional loss**: `SkillService` had zero imports — it was dead code. The `init_skills()` filesystem sync can be replaced by the existing UI/API for skill management.

3. **Frontend alignment**: The settings page referenced `/api/skills/node/{nodeId}` which never existed in the backend. Migrated to the existing `/api/skills/project/{project_id}` endpoints.

## Consequences

- Skills are managed exclusively via the Skills UI and `/api/skills` API endpoints.
- Filesystem-based `SKILL.md` files under `domains/automation/skills/` are no longer auto-synced to DB. Existing DB entries remain functional.
- `engine_setup.py` continues to load DB skills for prompt injection via `_load_prompt_components()`.
- Skill Mining (`skill_mining.py`) remains functional and writes directly to the DB `skills` table.

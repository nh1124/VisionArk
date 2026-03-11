"""Skill definitions for the LBS integration."""

from domains.orchestration2.engine.models.skill import SkillDef

SKILL_DEFS: list[SkillDef] = [
    SkillDef(
        name="lbs_planning",
        description="Manage LBS tasks, schedules, load, exceptions, and user condition",
        tools=[
            "list_tasks",
            "create_task",
            "update_task_details",
            "delete_task_by_id",
            "complete_lbs_task",
            "get_lbs_schedule",
            "get_load_on_day",
            "get_load_in_period",
            "manage_task_exception",
            "list_task_exceptions",
            "get_current_condition",
            "update_user_condition",
            "get_task_execution_history",
            "reset_user_condition",
        ],
        instructions="""\
## LBS Planning Skill

Use this skill when the user wants to plan, track, or adjust recurring/one-time tasks in LBS.
This includes task CRUD, daily completion, load analysis, exception handling, and condition-based load tuning.

### Core Operating Rules
1. Always confirm the target task and target date before mutating data.
2. Prefer read-first flow (`list_tasks`, `get_lbs_schedule`, `get_load_*`) before write operations.
3. For one-day changes, use exceptions (`manage_task_exception`) instead of changing base recurrence.
4. For recurring structure changes (name/rule/workload), use `update_task_details`.
5. Treat completion (`complete_lbs_task`) and metadata update (`update_task_details`) as separate intents.

### Standard Workflows

#### A) Review and summarize current plan
1. Call `list_tasks` (optionally with context filter).
2. If date-specific planning is needed, call `get_lbs_schedule(start_date, end_date)`.
3. If balancing is requested, call `get_load_on_day` or `get_load_in_period`.
4. Summarize bottlenecks: overloaded days, locked tasks, exception-heavy tasks.

#### B) Create a new task safely
1. Collect: `task_name`, `workload`, `rule_type`, and date/rule parameters.
2. Call `create_task`.
3. Re-check with `list_tasks` or `get_lbs_schedule` and report placement impact.
4. If user asks "just this day", do not create a new recurring task; use exception flow.

#### C) Adjust an existing task
1. Resolve task from `list_tasks` first.
2. If changing base properties (name/workload/context/notes), call `update_task_details`.
3. If changing only one day, call `manage_task_exception` with create/update.
4. Re-check with `get_lbs_schedule` for the affected date range.

#### D) Mark execution result
1. Call `complete_lbs_task(task_id, target_date, status)`.
2. If status semantics are unclear, default to `done` only after confirmation.
3. Optionally inspect trend using `get_task_execution_history`.

#### E) Operate daily overrides (exceptions)
1. Create override: `manage_task_exception(action="create", ...)`.
2. Modify override: `manage_task_exception(action="update", ...)`.
3. Remove override: `manage_task_exception(action="delete", ...)`.
4. Audit with `list_task_exceptions(start_date, end_date, task_id?)`.

### Tool Selection Guide
- Need full task list or context filter: `list_tasks`
- Need create/update/delete base task: `create_task` / `update_task_details` / `delete_task_by_id`
- Need completion state for a date: `complete_lbs_task`
- Need schedule overview: `get_lbs_schedule`
- Need load on one day or range: `get_load_on_day` / `get_load_in_period`
- Need one-day force/skip/override: `manage_task_exception`
- Need exceptions audit: `list_task_exceptions`
- Need condition-based adjustment input: `get_current_condition` / `update_user_condition` / `reset_user_condition`
- Need historical execution check: `get_task_execution_history`

### Condition and Load Policy
1. If the user reports fatigue or low capacity, update with `update_user_condition`.
2. Re-check projected load (`get_load_on_day` or period) after condition change.
3. Use temporary exceptions for acute disruptions; avoid rewriting long-term recurrence unless requested.
4. If user asks to clear condition effects for a date, use `reset_user_condition`.

### Error Handling and Recovery
1. If task ID is ambiguous, re-run `list_tasks` and present candidate IDs.
2. If date format is invalid, request ISO date (`YYYY-MM-DD`) and retry.
3. If a daily override operation fails, inspect with `list_task_exceptions` for that date first.
4. If completion update appears inconsistent, validate with schedule/history tools before retrying.

### Communication Contract
For every mutating operation, report:
1. What changed (task/date/action).
2. What tool was executed.
3. Post-change verification result (task list/schedule/load/exception snapshot).
4. Any remaining risk or follow-up action (e.g., overloaded day still unresolved).
""",
    ),
]

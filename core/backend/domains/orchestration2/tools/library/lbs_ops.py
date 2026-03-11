"""Native orchestration2 tools for LBS operations."""

from __future__ import annotations

from datetime import date
from typing import Any

from domains.identity.sync_coordinator import SyncCoordinator
from domains.lbs.client import TaskStatus, get_lbs_client
from domains.orchestration2.engine.models.execution import ExecutionContext, ToolResult
from domains.orchestration2.engine.models.message import ToolCallRef
from domains.orchestration2.engine.models.tool import ToolDef
from domains.orchestration2.tools.base import fail, get_db, get_user_id, make_result


def _user_settings(ctx: ExecutionContext) -> dict[str, Any]:
    settings = ctx.metadata.get("user_settings")
    return settings if isinstance(settings, dict) else {}


def _context_name(ctx: ExecutionContext) -> str:
    return str(_user_settings(ctx).get("context_name") or "general")


def _timezone(ctx: ExecutionContext) -> str:
    return str(_user_settings(ctx).get("timezone") or "UTC")


def _to_iso(d: str) -> str:
    # Validate date format early and return canonical ISO string.
    return date.fromisoformat(d).isoformat()


def _task_line(task: dict[str, Any]) -> str:
    status = task.get("status", "todo")
    locked = " [LOCKED]" if task.get("is_locked") else ""
    overwritten = " [OVERWRITTEN]" if task.get("has_exception") else ""
    return f"- [{task.get('task_id')}] {task.get('task_name')} ({task.get('rule_type')}) [{status}]{locked}{overwritten}"


class ListTasksTool:
    definition = ToolDef(
        name="list_tasks",
        description="List active tasks from the LBS system for the current or a specific context. "
        "HOW TO USE: 'list_tasks()' to see all active tasks, or 'list_tasks(context=\"research\")' to filter.",
        parameters={
            "type": "object",
            "properties": {
                "context": {"type": "string", "description": "Filter by context/project name"},
                "target_date": {"type": "string", "description": "Optional YYYY-MM-DD (reserved for future merge view)"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        context = call.arguments.get("context")

        try:
            client = await get_lbs_client(user_id, db)
            tasks = await client.list_tasks(context=context)
            if not tasks:
                return make_result(call, f"No tasks for {context or 'all contexts'}.")

            lines = [f"Found {len(tasks)} task(s):"]
            lines.extend(_task_line(t) for t in tasks)
            return make_result(call, "\n".join(lines))
        except Exception as exc:
            return fail(call, f"Failed to list tasks: {exc}")


class CreateTaskTool:
    definition = ToolDef(
        name="create_task",
        description="Create a new task in the LBS system with a specific recurrence rule. "
        "ATTENTION: 'workload' is a score from 1-10 representing estimated cognitive load. "
        "HOW TO USE: 'create_task(task_name=\"Analyze Log\", workload=3.0, rule_type=\"ONCE\", due_date=\"2025-12-01\")'.",
        parameters={
            "type": "object",
            "properties": {
                "task_name": {"type": "string", "description": "Name of the task"},
                "workload": {"type": "number", "description": "Estimated load score (1-10)"},
                "context": {"type": "string", "description": "Context/project name"},
                "rule_type": {"type": "string", "description": "ONCE | WEEKLY | EVERY_N_DAYS | MONTHLY_DAY"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD for ONCE"},
                "days": {"type": "string", "description": "Comma-separated days for WEEKLY, e.g. mon,wed,fri"},
                "interval_days": {"type": "integer", "description": "Interval for EVERY_N_DAYS"},
                "month_day": {"type": "integer", "description": "Day of month for MONTHLY_DAY"},
                "start_time": {"type": "string", "description": "HH:MM"},
                "end_time": {"type": "string", "description": "HH:MM"},
                "is_locked": {"type": "boolean", "description": "Lock from AI modifications"},
                "metadata": {"type": "object", "description": "Optional metadata"},
                "notes": {"type": "string", "description": "Optional notes"},
            },
            "required": ["task_name", "workload"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        args = call.arguments

        task_name = args.get("task_name")
        workload = args.get("workload")
        if task_name is None or workload is None:
            return fail(call, "task_name and workload are required.")

        rule_type = str(args.get("rule_type", "ONCE")).upper()
        payload: dict[str, Any] = {
            "task_name": str(task_name),
            "context": args.get("context") or _context_name(ctx),
            "base_load_score": float(workload),
            "rule_type": rule_type,
            "active": True,
            "is_locked": bool(args.get("is_locked", False)),
            "metadata": args.get("metadata") or {},
            "notes": args.get("notes"),
            "timezone": _timezone(ctx),
        }

        if args.get("start_time"):
            payload["start_time"] = args.get("start_time")
        if args.get("end_time"):
            payload["end_time"] = args.get("end_time")

        if rule_type == "ONCE" and args.get("due_date"):
            payload["due_date"] = _to_iso(str(args.get("due_date")))
        elif rule_type == "WEEKLY" and args.get("days"):
            day_map = {d.strip().lower(): True for d in str(args.get("days")).split(",")}
            payload.update({k: day_map.get(k, False) for k in ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]})
        elif rule_type == "EVERY_N_DAYS":
            payload["interval_days"] = args.get("interval_days")
        elif rule_type == "MONTHLY_DAY":
            payload["month_day"] = args.get("month_day")

        try:
            client = await get_lbs_client(user_id, db)
            res = await client.create_task(payload)
            await SyncCoordinator.trigger_export(db, user_id, reason="AI task creation")
            return make_result(call, f"Created task '{task_name}' (id: {res.get('task_id') or res.get('id', 'unknown')}).")
        except Exception as exc:
            return fail(call, f"Failed to create task: {exc}")


class UpdateTaskTool:
    definition = ToolDef(
        name="update_task_details",
        description="Update the metadata (name, workload, context, notes) of an existing task. "
        "HOW TO USE: 'update_task_details(task_id=\"...\", workload=5.0)'.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "task_name": {"type": "string"},
                "workload": {"type": "number"},
                "context": {"type": "string"},
                "start_time": {"type": "string", "description": "HH:MM"},
                "end_time": {"type": "string", "description": "HH:MM"},
                "is_locked": {"type": "boolean"},
                "metadata": {"type": "object"},
                "notes": {"type": "string"},
            },
            "required": ["task_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        args = call.arguments
        task_id = args.get("task_id")
        if not task_id:
            return fail(call, "task_id is required.")

        updates = {k: v for k, v in args.items() if k != "task_id" and v is not None}
        if "workload" in updates:
            updates["base_load_score"] = float(updates.pop("workload"))
        updates.setdefault("timezone", _timezone(ctx))

        if not updates:
            return fail(call, "No changes provided.")

        try:
            client = await get_lbs_client(user_id, db)
            await client.update_task(str(task_id), updates)
            await SyncCoordinator.trigger_export(db, user_id, reason="AI task update")
            return make_result(call, f"Updated task {task_id}.")
        except Exception as exc:
            return fail(call, f"Failed to update task: {exc}")


class DeleteTaskTool:
    definition = ToolDef(
        name="delete_task_by_id",
        description="Delete a task from the LBS system permanently. "
        "HOW TO USE: 'delete_task_by_id(task_id=\"...\")'.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
            },
            "required": ["task_id"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        task_id = call.arguments.get("task_id")
        if not task_id:
            return fail(call, "task_id is required.")

        try:
            client = await get_lbs_client(user_id, db)
            await client.delete_task(str(task_id))
            await SyncCoordinator.trigger_export(db, user_id, reason="AI task deletion")
            return make_result(call, f"Deleted task {task_id}.")
        except Exception as exc:
            return fail(call, f"Failed to delete task: {exc}")


class CompleteLBSTaskTool:
    definition = ToolDef(
        name="complete_lbs_task",
        description="Mark an LBS task as completed, skipped, or partially done for a specific date. "
        "HOW TO USE: 'complete_lbs_task(task_id=\"...\", target_date=\"2025-01-20\", status=\"done\")'.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                "status": {"type": "string", "description": "done | skipped | todo"},
            },
            "required": ["task_id", "target_date"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        task_id = call.arguments.get("task_id")
        target_date = call.arguments.get("target_date")
        status_raw = str(call.arguments.get("status", "done")).lower()

        if not task_id or not target_date:
            return fail(call, "task_id and target_date are required.")

        try:
            status = TaskStatus(status_raw)
        except Exception:
            return fail(call, "status must be one of: todo, done, skipped.")

        try:
            d = _to_iso(str(target_date))
            client = await get_lbs_client(user_id, db)
            await client.toggle_task_completion(str(task_id), d, status)
            await SyncCoordinator.trigger_export(db, user_id, reason="AI task completion update")
            return make_result(call, f"Marked task {task_id} as {status.value} on {d}.")
        except Exception as exc:
            return fail(call, f"Failed to complete task: {exc}")


class GetLBSScheduleTool:
    definition = ToolDef(
        name="get_lbs_schedule",
        description="Get LBS schedule for a date range.",
        parameters={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        start_date = call.arguments.get("start_date")
        end_date = call.arguments.get("end_date")
        if not start_date or not end_date:
            return fail(call, "start_date and end_date are required.")

        try:
            s = _to_iso(str(start_date))
            e = _to_iso(str(end_date))
            client = await get_lbs_client(user_id, db)
            schedule = await client.get_schedule(s, e)
            return make_result(call, f"Schedule found ({len(schedule)} day entries) for {s} to {e}.")
        except Exception as exc:
            return fail(call, f"Failed to get schedule: {exc}")


class GetLoadOnDayTool:
    definition = ToolDef(
        name="get_load_on_day",
        description="Calculate load score for a specific day.",
        parameters={
            "type": "object",
            "properties": {
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["target_date"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        target_date = call.arguments.get("target_date")
        if not target_date:
            return fail(call, "target_date is required.")

        try:
            d = _to_iso(str(target_date))
            client = await get_lbs_client(user_id, db)
            res = await client.calculate_load(d)
            adjusted = res.get("adjusted_load")
            return make_result(call, f"Load on {d}: {adjusted}")
        except Exception as exc:
            return fail(call, f"Failed to get load: {exc}")


class GetLoadInPeriodTool:
    definition = ToolDef(
        name="get_load_in_period",
        description="Get load heatmap for a date range.",
        parameters={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["start_date", "end_date"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        start_date = call.arguments.get("start_date")
        end_date = call.arguments.get("end_date")
        if not start_date or not end_date:
            return fail(call, "start_date and end_date are required.")

        try:
            s = _to_iso(str(start_date))
            e = _to_iso(str(end_date))
            client = await get_lbs_client(user_id, db)
            heatmap = await client.get_heatmap(s, e)
            return make_result(call, f"Heatmap found ({len(heatmap)} day entries) for {s} to {e}.")
        except Exception as exc:
            return fail(call, f"Failed to get heatmap: {exc}")


class ManageTaskExceptionTool:
    definition = ToolDef(
        name="manage_task_exception",
        description="Create, update, or delete a task exception for a specific date (Daily Override). "
        "HOW TO USE: 'manage_task_exception(task_id=\"...\", target_date=\"2025-01-20\", action=\"create\", exception_type=\"FORCE_DO\")'.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                "action": {"type": "string", "description": "create | update | delete"},
                "exception_type": {"type": "string", "description": "SKIP | OVERRIDE_LOAD | FORCE_DO | MANUAL_LOCK"},
                "override_load_value": {"type": "number", "description": "Override load value"},
                "start_time": {"type": "string", "description": "HH:MM"},
                "end_time": {"type": "string", "description": "HH:MM"},
                "is_locked": {"type": "boolean", "description": "Lock this daily occurrence"},
                "notes": {"type": "string", "description": "Optional notes"},
            },
            "required": ["task_id", "target_date"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        args = dict(call.arguments)

        action = str(args.pop("action", "create")).lower()
        task_id = args.get("task_id")
        target_date = args.get("target_date")

        if not task_id or not target_date:
            return fail(call, "task_id and target_date are required.")

        try:
            d = _to_iso(str(target_date))
            client = await get_lbs_client(user_id, db)

            if action == "create":
                payload = {k: v for k, v in args.items() if v is not None}
                payload["target_date"] = d
                res = await client.create_exception(payload)
                return make_result(call, f"Created exception for task {task_id} on {d} (id: {res.get('id', 'unknown')}).")

            exceptions = await client.get_exceptions(d, d)
            exc = next((e for e in exceptions if e.get("task_id") == task_id), None)
            if not exc:
                return fail(call, f"No exception found for task {task_id} on {d}.")
            exception_id = exc.get("id")

            if action == "update":
                payload = {k: v for k, v in args.items() if v is not None}
                payload["target_date"] = d
                await client.update_exception(exception_id, payload)
                return make_result(call, f"Updated exception {exception_id} for task {task_id}.")

            if action == "delete":
                await client.delete_exception(exception_id)
                return make_result(call, f"Deleted exception {exception_id} for task {task_id}.")

            return fail(call, "action must be one of: create, update, delete.")
        except Exception as exc:
            return fail(call, f"Failed to manage exception: {exc}")


class ListExceptionsTool:
    definition = ToolDef(
        name="list_task_exceptions",
        description="List all task exceptions (daily overrides) for a given date range.",
        parameters={
            "type": "object",
            "properties": {
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
                "task_id": {"type": "string", "description": "Optional task ID filter"},
            },
            "required": ["start_date", "end_date"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        start_date = call.arguments.get("start_date")
        end_date = call.arguments.get("end_date")
        task_id = call.arguments.get("task_id")

        if not start_date or not end_date:
            return fail(call, "start_date and end_date are required.")

        try:
            s = _to_iso(str(start_date))
            e = _to_iso(str(end_date))
            client = await get_lbs_client(user_id, db)
            excs = await client.get_exceptions(s, e)
            if task_id:
                excs = [ex for ex in excs if ex.get("task_id") == task_id]
            return make_result(call, f"Found {len(excs)} exception(s) from {s} to {e}.")
        except Exception as exc:
            return fail(call, f"Failed to list exceptions: {exc}")


class GetCurrentConditionTool:
    definition = ToolDef(
        name="get_current_condition",
        description="Retrieve user's condition for a specific date (default: today).",
        parameters={
            "type": "object",
            "properties": {
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        target_date = call.arguments.get("target_date")

        try:
            d = date.today().isoformat() if not target_date else _to_iso(str(target_date))
            client = await get_lbs_client(user_id, db)
            res = await client.get_condition(d)
            return make_result(call, f"Condition for {d}: {res}")
        except Exception as exc:
            return fail(call, f"Failed to get condition: {exc}")


class UpdateUserConditionTool:
    definition = ToolDef(
        name="update_user_condition",
        description="Report the user's current cognitive fatigue level to LBS for dynamic load adjustment.",
        parameters={
            "type": "object",
            "properties": {
                "cognitive_fatigue": {"type": "integer", "description": "Fatigue level (1-10)"},
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
                "notes": {"type": "string", "description": "Optional notes"},
            },
            "required": ["cognitive_fatigue"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        fatigue = call.arguments.get("cognitive_fatigue")
        target_date = call.arguments.get("target_date")
        notes = call.arguments.get("notes")

        if fatigue is None:
            return fail(call, "cognitive_fatigue is required.")

        try:
            d = date.today().isoformat() if not target_date else _to_iso(str(target_date))
            client = await get_lbs_client(user_id, db)
            await client.update_condition(d, int(fatigue), notes)
            return make_result(call, f"Condition updated for {d}.")
        except Exception as exc:
            return fail(call, f"Failed to update condition: {exc}")


class GetTaskHistoryTool:
    definition = ToolDef(
        name="get_task_execution_history",
        description="Get execution history for a task across a date range.",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {"type": "string", "description": "Task ID"},
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": ["task_id", "start_date", "end_date"],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        task_id = call.arguments.get("task_id")
        start_date = call.arguments.get("start_date")
        end_date = call.arguments.get("end_date")

        if not task_id or not start_date or not end_date:
            return fail(call, "task_id, start_date, and end_date are required.")

        try:
            s = _to_iso(str(start_date))
            e = _to_iso(str(end_date))
            client = await get_lbs_client(user_id, db)
            history = await client.get_task_history(str(task_id), s, e)
            return make_result(call, f"Found {len(history)} history record(s) for task {task_id}.")
        except Exception as exc:
            return fail(call, f"Failed to get history: {exc}")


class ResetUserConditionTool:
    definition = ToolDef(
        name="reset_user_condition",
        description="Delete user's condition report for a specific date (default: today).",
        parameters={
            "type": "object",
            "properties": {
                "target_date": {"type": "string", "description": "YYYY-MM-DD"},
            },
            "required": [],
        },
    )

    async def invoke(self, call: ToolCallRef, ctx: ExecutionContext) -> ToolResult:
        db = get_db(ctx)
        user_id = get_user_id(ctx)
        target_date = call.arguments.get("target_date")

        try:
            d = date.today().isoformat() if not target_date else _to_iso(str(target_date))
            client = await get_lbs_client(user_id, db)
            await client.delete_condition(d)
            return make_result(call, f"Reset condition for {d}.")
        except Exception as exc:
            return fail(call, f"Failed to reset condition: {exc}")

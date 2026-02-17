from va_sdk import BaseTool, BaseModel, IntegrationContext
from integrations.lbs.client import get_lbs_client, TaskStatus
from domains.identity.sync_coordinator import SyncCoordinator
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Any, Optional, Dict
from datetime import date

from pydantic import Field  

class ListTasksArgs(BaseModel):
    context: Optional[str] = Field(None, description="Filter by context/project name")
    target_date: Optional[str] = Field(None, description="YYYY-MM-DD to see merged status/overrides for a specific day")

class ListTasksTool(BaseTool):
    name = "list_tasks"
    description = (
        "List active tasks from the LBS system for the current or a specific context. "
        "HOW TO USE: 'list_tasks()' to see all active tasks, or 'list_tasks(context=\"research\")' to filter."
    )
    args_schema = ListTasksArgs

    async def run(self, context: Optional[str] = None, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            client = await get_lbs_client(user_id, db_session)
            tasks = await client.list_tasks(
                context=context
            )
            if not tasks:
                return ToolResult(
                    content=f"No tasks for {context or 'all contexts'}.",
                    data={"tasks": []}
                )
            
            lines = []
            for t in tasks:
                status = f" [{t.get('status', 'todo')}]"
                locked = " [LOCKED]" if t.get("is_locked") else ""
                exc = " [OVERWRITTEN]" if t.get("has_exception") else ""
                lines.append(f"• [{t['task_id']}] {t['task_name']} ({t.get('rule_type')}){status}{locked}{exc}")
            
            return ToolResult(
                content="Tasks:\n" + "\n".join(lines),
                data={"tasks": tasks}
            )
        except Exception as e:
            return ToolResult(content=f"Failed to list tasks: {e}", is_success=False)

class CreateTaskArgs(BaseModel):
    task_name: str = Field(..., description="Name of the task")
    workload: float = Field(..., description="Estimated load (1-10)")
    context: Optional[str] = Field(None, description="Context/Project name")
    rule_type: str = Field("ONCE", description="Recurrence type: ONCE, WEEKLY, EVERY_N_DAYS, MONTHLY_DAY")
    due_date: Optional[str] = Field(None, description="YYYY-MM-DD for ONCE tasks")
    days: Optional[str] = Field(None, description="Comma-separated days for WEEKLY (mon,tue,...)")
    interval_days: Optional[int] = Field(None, description="Interval in days for EVERY_N_DAYS")
    month_day: Optional[int] = Field(None, description="Day of month for MONTHLY_DAY")
    start_time: Optional[str] = Field(None, description="Start time (HH:MM)")
    end_time: Optional[str] = Field(None, description="End time (HH:MM)")
    is_locked: bool = Field(False, description="Lock this task from AI modifications")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional custom metadata (e.g., {'va_intent': {...}})")
    notes: Optional[str] = None

class CreateTaskTool(BaseTool):
    name = "create_task"
    description = (
        "Create a new task in the LBS system with a specific recurrence rule. "
        "ATTENTION: 'workload' is a score from 1-10 representing estimated cognitive load. "
        "HOW TO USE: 'create_task(task_name=\"Analyze Log\", workload=3.0, rule_type=\"ONCE\", due_date=\"2025-12-01\")'."
    )
    args_schema = CreateTaskArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        context_name = ctx.user_settings.get("context_name", "general")
        
        try:
            client = await get_lbs_client(user_id, db_session)
            task_name = kwargs.get("task_name")
            context = kwargs.get("context")
            workload = kwargs.get("workload")
            rule_type = kwargs.get("rule_type", "ONCE").upper()
            
            data = {
                "task_name": task_name,
                "context": context or context_name,
                "base_load_score": float(workload),
                "rule_type": rule_type,
                "active": True,
                "is_locked": kwargs.get("is_locked", False),
                "metadata": kwargs.get("metadata") or {},
                "notes": kwargs.get("notes")
            }
            
            if kwargs.get("start_time"): data["start_time"] = kwargs.get("start_time")
            if kwargs.get("end_time"): data["end_time"] = kwargs.get("end_time")
            
            if rule_type == "ONCE" and kwargs.get("due_date"):
                data["due_date"] = kwargs.get("due_date")
            elif rule_type == "WEEKLY" and kwargs.get("days"):
                dm = {d.strip().lower(): True for d in kwargs.get("days").split(",")}
                data.update({k: dm.get(k, False) for k in ["mon","tue","wed","thu","fri","sat","sun"]})
            elif rule_type == "EVERY_N_DAYS":
                data["interval_days"] = kwargs.get("interval_days")
            elif rule_type == "MONTHLY_DAY":
                data["month_day"] = kwargs.get("month_day")
                
            res = await client.create_task(data)
            # Trigger Export
            await SyncCoordinator.trigger_export(db_session, user_id, reason="AI task creation")
            return ToolResult(content=f"✅ Created task {task_name}", data=res)
        except Exception as e:
            return ToolResult(content=f"Failed to create task: {e}", is_success=False)

class UpdateTaskArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task to update")
    task_name: Optional[str] = None
    workload: Optional[float] = None
    context: Optional[str] = None
    start_time: Optional[str] = Field(None, description="Start time (HH:MM)")
    end_time: Optional[str] = Field(None, description="End time (HH:MM)")
    is_locked: Optional[bool] = Field(None, description="Lock/Unlock this task")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional custom metadata")
    notes: Optional[str] = None

class UpdateTaskTool(BaseTool):
    name = "update_task_details"
    description = (
        "Update the metadata (name, workload, context, notes) of an existing task. "
        "HOW TO USE: 'update_task_details(task_id=\"...\", workload=5.0)'."
    )
    args_schema = UpdateTaskArgs

    async def run(self, task_id: str, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            client = await get_lbs_client(user_id, db_session)
            upd = {k: v for k,v in kwargs.items() if v is not None}
            if 'workload' in upd: upd['base_load_score'] = float(upd.pop('workload'))
            
            if not upd:
                return ToolResult(content="No changes provided", is_success=False)
                
            await client.update_task(task_id, upd)
            # Trigger Export
            await SyncCoordinator.trigger_export(db_session, user_id, reason="AI task update")
            return ToolResult(content=f"Updated task {task_id}")
        except Exception as e:
            return ToolResult(content=f"Failed to update task: {e}", is_success=False)

class DeleteTaskArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task to delete")

class DeleteTaskTool(BaseTool):
    name = "delete_task_by_id"
    description = (
        "Delete a task from the LBS system permanently. "
        "HOW TO USE: 'delete_task_by_id(task_id=\"...\")'."
    )
    args_schema = DeleteTaskArgs

    async def run(self, task_id: str, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            client = await get_lbs_client(user_id, db_session)
            await client.delete_task(task_id)
            # Trigger Export
            await SyncCoordinator.trigger_export(db_session, user_id, reason="AI task deletion")
            return ToolResult(content=f"Deleted task {task_id}")
        except Exception as e:
            return ToolResult(content=f"Failed to delete task: {e}", is_success=False)

class CompleteLBSTaskArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task")
    target_date: str = Field(..., description="YYYY-MM-DD")
    status: str = Field("done", description="Status (done, skipped, partial)")

class CompleteLBSTaskTool(BaseTool):
    name = "complete_lbs_task"
    description = (
        "Mark an LBS task as completed, skipped, or partially done for a specific date. "
        "HOW TO USE: 'complete_lbs_task(task_id=\"...\", target_date=\"2025-01-20\", status=\"done\")'."
    )
    args_schema = CompleteLBSTaskArgs

    async def run(self, task_id: str, target_date: str, status: str = "done", ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            client = await get_lbs_client(user_id, db_session)
            await client.toggle_task_completion(task_id, date.fromisoformat(target_date), TaskStatus(status))
            # Trigger Export
            await SyncCoordinator.trigger_export(db_session, user_id, reason="AI task completion update")
            return ToolResult(content=f"Marked {task_id} as {status} for {target_date}")
        except Exception as e:
            return ToolResult(content=f"Failed to complete task: {e}", is_success=False)

class GetLBSScheduleArgs(BaseModel):
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")

class GetLBSScheduleTool(BaseTool):
    name = "get_lbs_schedule"
    description = "Get the LBS schedule for a specific date range."
    args_schema = GetLBSScheduleArgs

    async def run(self, start_date: str, end_date: str, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            client = await get_lbs_client(user_id, db_session)
            sch = await client.get_schedule(date.fromisoformat(start_date), date.fromisoformat(end_date))
            return ToolResult(content=f"Schedule found ({len(sch)} days)", data={"schedule": sch})
        except Exception as e:
            return ToolResult(content=f"Failed to get schedule: {e}", is_success=False)

class GetLoadOnDayArgs(BaseModel):
    target_date: str = Field(..., description="YYYY-MM-DD")

class GetLoadOnDayTool(BaseTool):
    name = "get_load_on_day"
    description = "Calculate the load score for a specific day."
    args_schema = GetLoadOnDayArgs

    async def run(self, target_date: str, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        if not db_session or not user_id:
            return ToolResult(content="Context error", is_success=False)
        
        try:
            client = await get_lbs_client(user_id, db_session)
            res = await client.calculate_load(date.fromisoformat(target_date))
            return ToolResult(content=f"Load: {res.get('adjusted_load')}", data=res)
        except Exception as e:
            return ToolResult(content=f"Failed to get load: {e}", is_success=False)

class GetLoadInPeriodArgs(BaseModel):
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")

class GetLoadInPeriodTool(BaseTool):
    name = "get_load_in_period"
    description = "Get the load heatmap for a specific date range."
    args_schema = GetLoadInPeriodArgs

    async def run(self, start_date: str, end_date: str, ctx: IntegrationContext = None, **kwargs) -> Any:
        if not ctx: return {"success": False, "message": "Context error"}
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            from va_sdk import ToolResult
            client = await get_lbs_client(user_id, db_session)
            hm = await client.get_heatmap(date.fromisoformat(start_date), date.fromisoformat(end_date))
            return ToolResult(content=f"Heatmap: {len(hm)} days", data={"heatmap": hm})
        except Exception as e:
            return ToolResult(content=f"Failed to get heatmap: {e}", is_success=False)

class ManageTaskExceptionArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task")
    target_date: str = Field(..., description="YYYY-MM-DD")
    action: str = Field("create", description="Action: create, update, delete")
    exception_type: Optional[str] = Field(None, description="SKIP, OVERRIDE_LOAD, FORCE_DO, MANUAL_LOCK")
    override_load_value: Optional[float] = Field(None, description="New load value for this day")
    start_time: Optional[str] = Field(None, description="Start time override (HH:MM)")
    end_time: Optional[str] = Field(None, description="End time override (HH:MM)")
    is_locked: bool = Field(False, description="Lock this daily occurrence")
    notes: Optional[str] = None

class ManageTaskExceptionTool(BaseTool):
    name = "manage_task_exception"
    description = (
        "Create, update, or delete a task exception for a specific date (Daily Override). "
        "HOW TO USE: 'manage_task_exception(task_id=\"...\", target_date=\"2025-01-20\", action=\"create\", exception_type=\"FORCE_DO\")'."
    )
    args_schema = ManageTaskExceptionArgs

    async def run(self, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            client = await get_lbs_client(user_id, db_session)
            action = kwargs.pop("action").lower()
            task_id = kwargs.get("task_id")
            target_date = kwargs.get("target_date")
            
            if action == "create":
                data = {k: v for k, v in kwargs.items() if v is not None}
                res = await client.create_exception(data)
                return ToolResult(content=f"Created exception for {task_id} on {target_date}", data=res)
            
            excs = await client.get_exceptions(target_date, target_date)
            exc = next((e for e in excs if e.get("task_id") == task_id), None)
            
            if not exc:
                return ToolResult(content=f"No exception found for {task_id} on {target_date}", is_success=False)
            
            exc_id = exc["id"]
            
            if action == "update":
                data = {k: v for k, v in kwargs.items() if v is not None}
                await client.update_exception(exc_id, data)
                return ToolResult(content=f"Updated exception {exc_id} for {task_id}")
            elif action == "delete":
                await client.delete_exception(exc_id)
                return ToolResult(content=f"Deleted exception {exc_id} for {task_id}")
            else:
                return ToolResult(content=f"Unknown action: {action}", is_success=False)
                
        except Exception as e:
            return ToolResult(content=f"Failed to manage exception: {e}", is_success=False)

class ListExceptionsArgs(BaseModel):
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    task_id: Optional[str] = Field(None, description="Filter by task ID")

class ListExceptionsTool(BaseTool):
    name = "list_task_exceptions"
    description = "List all task exceptions (daily overrides) for a given date range."
    args_schema = ListExceptionsArgs

    async def run(self, start_date: str, end_date: str, task_id: Optional[str] = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        db_session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not db_session or not user_id:
            return ToolResult(content="Context error", is_success=False)
        
        try:
            client = await get_lbs_client(user_id, db_session)
            excs = await client.get_exceptions(date.fromisoformat(start_date), date.fromisoformat(end_date))
            if task_id:
                excs = [e for e in excs if e.get("task_id") == task_id]
            
            return ToolResult(content=f"Found {len(excs)} exceptions.", data={"exceptions": excs})
        except Exception as e:
            return ToolResult(content=f"Failed to list exceptions: {e}", is_success=False)

# --- Condition Tools ---

class GetCurrentConditionArgs(BaseModel):
    target_date: Optional[str] = Field(None, description="YYYY-MM-DD. Defaults to today.")

class GetCurrentConditionTool(BaseTool):
    name = "get_current_condition"
    description = "Retrieve the user's reported cognitive or physical condition for a specific date."
    args_schema = GetCurrentConditionArgs

    async def run(self, target_date: Optional[str] = None, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        try:
            d = date.fromisoformat(target_date) if target_date else date.today()
            client = await get_lbs_client(user_id, db_session)
            async with client:
                res = await client.get_condition(d)
                return ToolResult(content=f"Condition for {d}: {res}", data=res)
        except Exception as e:
            return ToolResult(content=f"Failed to get condition: {e}", is_success=False)

class UpdateUserConditionArgs(BaseModel):
    cognitive_fatigue: int = Field(..., description="Cognitive fatigue level (1-10, where 10 is max fatigue)")
    target_date: Optional[str] = Field(None, description="YYYY-MM-DD. Defaults to today.")
    notes: Optional[str] = Field(None, description="Additional context about the condition")

class UpdateUserConditionTool(BaseTool):
    name = "update_user_condition"
    description = "Report the user's current cognitive fatigue level to LBS for dynamic load adjustment."
    args_schema = UpdateUserConditionArgs

    async def run(self, cognitive_fatigue: int, target_date: Optional[str] = None, notes: Optional[str] = None, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            d = date.fromisoformat(target_date) if target_date else date.today()
            client = await get_lbs_client(user_id, db_session)
            async with client:
                res = await client.update_condition(d, cognitive_fatigue, notes)
                return ToolResult(content=f"✅ Condition updated for {d}.", data=res)
        except Exception as e:
            return ToolResult(content=f"Failed to update condition: {e}", is_success=False)

class GetTaskHistoryArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task")
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")

class GetTaskHistoryTool(BaseTool):
    name = "get_task_execution_history"
    description = "Get the historical execution records for a specific task over a date range."
    args_schema = GetTaskHistoryArgs

    async def run(self, task_id: str, start_date: str, end_date: str, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            client = await get_lbs_client(user_id, db_session)
            history = await client.get_task_history(task_id, date.fromisoformat(start_date), date.fromisoformat(end_date))
            return ToolResult(content=f"Found {len(history)} records.", data={"history": history})
        except Exception as e:
            return ToolResult(content=f"Failed to get history: {e}", is_success=False)

class ResetUserConditionArgs(BaseModel):
    target_date: Optional[str] = Field(None, description="YYYY-MM-DD. Defaults to today.")

class ResetUserConditionTool(BaseTool):
    name = "reset_user_condition"
    description = "Clear the user's condition report for a specific date."
    args_schema = ResetUserConditionArgs

    async def run(self, target_date: Optional[str] = None, ctx: IntegrationContext = None, **kwargs) -> Any:
        from va_sdk import ToolResult
        if not ctx: return ToolResult(content="Context error", is_success=False)
        db_session = ctx.db
        user_id = ctx.user_id
        
        try:
            d = date.fromisoformat(target_date) if target_date else date.today()
            client = await get_lbs_client(user_id, db_session)
            async with client:
                await client.delete_condition(d)
                return ToolResult(content=f"Reset condition for {d}.")
        except Exception as e:
            return ToolResult(content=f"Failed to reset condition: {e}", is_success=False)

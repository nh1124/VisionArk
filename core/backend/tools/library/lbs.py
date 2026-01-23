from typing import Any, Optional, Dict
from pydantic import BaseModel, Field
from datetime import date
from tools.base import BaseTool
from tools.utils import get_lbs_client
from sqlalchemy.ext.asyncio import AsyncSession

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

    async def run(self, context: Optional[str] = None, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        context_name: str = kwargs.get("context_name", "general")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            target_date = kwargs.get("target_date")
            tasks = await client.list_tasks(
                context=context or context_name,
                target_date=target_date
            )
            if not tasks:
                return {"success": True, "message": f"No tasks for {context or context_name}.", "data": {"tasks": []}}
            
            lines = []
            for t in tasks:
                status = f" [{t.get('status', 'todo')}]" if target_date else ""
                locked = " [LOCKED]" if t.get("is_locked") else ""
                exc = " [OVERWRITTEN]" if t.get("has_exception") else ""
                lines.append(f"• [{t['task_id']}] {t['task_name']} ({t.get('rule_type')}){status}{locked}{exc}")
            
            return {"success": True, "message": "Tasks:\n" + "\n".join(lines), "data": {"tasks": tasks}}
        except Exception as e:
            return {"success": False, "message": f"Failed to list tasks: {e}"}

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
    notes: Optional[str] = Field(None, description="Additional notes")

class CreateTaskTool(BaseTool):
    name = "create_task"
    description = (
        "Create a new task in the LBS system with a specific recurrence rule. "
        "ATTENTION: 'workload' is a score from 1-10 representing estimated cognitive load. "
        "HOW TO USE: 'create_task(task_name=\"Analyze Log\", workload=3.0, rule_type=\"ONCE\", due_date=\"2025-12-01\")'."
    )
    args_schema = CreateTaskArgs

    async def run(self, **kwargs) -> Any:
        session: AsyncSession = kwargs.pop("db_session", None)
        user_id: str = kwargs.pop("user_id", None)
        context_name: str = kwargs.pop("context_name", "general")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
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
            return {"success": True, "message": f"✅ Created task {task_name}", "data": res}
        except Exception as e:
            return {"success": False, "message": f"Failed to create task: {e}"}

class UpdateTaskArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task to update")
    task_name: Optional[str] = None
    workload: Optional[float] = None
    context: Optional[str] = None
    start_time: Optional[str] = Field(None, description="Start time (HH:MM)")
    end_time: Optional[str] = Field(None, description="End time (HH:MM)")
    is_locked: Optional[bool] = Field(None, description="Lock/Unlock this task")
    notes: Optional[str] = None

class UpdateTaskTool(BaseTool):
    name = "update_task_details"
    description = (
        "Update the metadata (name, workload, context, notes) of an existing task. "
        "HOW TO USE: 'update_task_details(task_id=\"...\", workload=5.0)'."
    )
    args_schema = UpdateTaskArgs

    async def run(self, task_id: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.pop("db_session", None)
        user_id: str = kwargs.pop("user_id", None)
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            upd = {k: v for k,v in kwargs.items() if v is not None}
            if 'workload' in upd: upd['base_load_score'] = float(upd.pop('workload'))
            if 'context' in upd: upd['context'] = upd.pop('context')
            
            if not upd:
                return {"success": False, "message": "No changes provided"}
                
            await client.update_task(task_id, upd)
            return {"success": True, "message": f"Updated task {task_id}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to update task: {e}"}

class DeleteTaskArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task to delete")

class DeleteTaskTool(BaseTool):
    name = "delete_task_by_id"
    description = (
        "Delete a task from the LBS system permanently. "
        "ATTENTION: This action is IRREVERSIBLE. Use it only if a task was created by mistake. "
        "HOW TO USE: 'delete_task_by_id(task_id=\"...\")'."
    )
    args_schema = DeleteTaskArgs

    async def run(self, task_id: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            await client.delete_task(task_id)
            return {"success": True, "message": f"Deleted task {task_id}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to delete task: {e}"}

class CompleteLBSTaskArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task")
    target_date: str = Field(..., description="YYYY-MM-DD")
    status: str = Field("done", description="Status (done, skipped, partial)")

class CompleteLBSTaskTool(BaseTool):
    name = "complete_lbs_task"
    description = (
        "Mark an LBS task as completed, skipped, or partially done for a specific date. "
        "ATTENTION: 'target_date' must be in YYYY-MM-DD format. "
        "HOW TO USE: 'complete_lbs_task(task_id=\"...\", target_date=\"2025-01-20\", status=\"done\")'."
    )
    args_schema = CompleteLBSTaskArgs

    async def run(self, task_id: str, target_date: str, status: str = "done", **kwargs) -> Any:
        session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            from services.lbs_client import TaskStatus
            client = await get_lbs_client(user_id, session)
            await client.toggle_task_completion(task_id, date.fromisoformat(target_date), TaskStatus(status))
            return {"success": True, "message": f"Marked {task_id} as {status} for {target_date}"}
        except Exception as e:
            return {"success": False, "message": f"Failed to complete task: {e}"}

class GetLBSScheduleArgs(BaseModel):
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")

class GetLBSScheduleTool(BaseTool):
    name = "get_lbs_schedule"
    description = "Get the LBS schedule for a specific date range."
    args_schema = GetLBSScheduleArgs

    async def run(self, start_date: str, end_date: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            sch = await client.get_schedule(date.fromisoformat(start_date), date.fromisoformat(end_date))
            return {"success": True, "message": f"Schedule found ({len(sch)} days)", "data": {"schedule": sch}}
        except Exception as e:
            return {"success": False, "message": f"Failed to get schedule: {e}"}

class GetLoadOnDayArgs(BaseModel):
    target_date: str = Field(..., description="YYYY-MM-DD")

class GetLoadOnDayTool(BaseTool):
    name = "get_load_on_day"
    description = "Calculate the load score for a specific day."
    args_schema = GetLoadOnDayArgs

    async def run(self, target_date: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            res = await client.calculate_load(date.fromisoformat(target_date))
            return {"success": True, "message": f"Load: {res.get('adjusted_load')}", "data": res}
        except Exception as e:
            return {"success": False, "message": f"Failed to get load: {e}"}

class GetLoadInPeriodArgs(BaseModel):
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")

class GetLoadInPeriodTool(BaseTool):
    name = "get_load_in_period"
    description = "Get the load heatmap for a specific date range."
    args_schema = GetLoadInPeriodArgs

    async def run(self, start_date: str, end_date: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            hm = await client.get_heatmap(date.fromisoformat(start_date), date.fromisoformat(end_date))
            return {"success": True, "message": f"Heatmap: {len(hm)} days", "data": {"heatmap": hm}}
        except Exception as e:
            return {"success": False, "message": f"Failed to get heatmap: {e}"}
            
class GetTaskHistoryArgs(BaseModel):
    task_id: str = Field(..., description="ID of the task")
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")

class GetTaskHistoryTool(BaseTool):
    name = "get_task_execution_history"
    description = "Get the historical execution records for a specific task over a date range."
    args_schema = GetTaskHistoryArgs

    async def run(self, task_id: str, start_date: str, end_date: str, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            history = await client.get_task_history(task_id, date.fromisoformat(start_date), date.fromisoformat(end_date))
            return {"success": True, "message": f"Found {len(history)} records.", "data": {"history": history}}
        except Exception as e:
            return {"success": False, "message": f"Failed to get history: {e}"}

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

    async def run(self, **kwargs) -> Any:
        session: AsyncSession = kwargs.pop("db_session", None)
        user_id: str = kwargs.pop("user_id", None)
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            action = kwargs.pop("action").lower()
            task_id = kwargs.get("task_id")
            target_date = kwargs.get("target_date")
            
            if action == "create":
                data = {k: v for k, v in kwargs.items() if v is not None}
                res = await client.create_exception(data)
                return {"success": True, "message": f"Created exception for {task_id} on {target_date}", "data": res}
            
            # For update/delete, we need to find the exception ID first
            # LBS API requires exception_id for update/delete
            excs = await client.get_exceptions(target_date, target_date)
            exc = next((e for e in excs if e.get("task_id") == task_id), None)
            
            if not exc:
                return {"success": False, "message": f"No exception found for {task_id} on {target_date}"}
            
            exc_id = exc["id"]
            
            if action == "update":
                data = {k: v for k, v in args.items() if v is not None}
                await client.update_exception(exc_id, data)
                return {"success": True, "message": f"Updated exception {exc_id} for {task_id}"}
            elif action == "delete":
                await client.delete_exception(exc_id)
                return {"success": True, "message": f"Deleted exception {exc_id} for {task_id}"}
            else:
                return {"success": False, "message": f"Unknown action: {action}"}
                
        except Exception as e:
            return {"success": False, "message": f"Failed to manage exception: {e}"}

class ListExceptionsArgs(BaseModel):
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    task_id: Optional[str] = Field(None, description="Filter by task ID")

class ListExceptionsTool(BaseTool):
    name = "list_task_exceptions"
    description = "List all task exceptions (daily overrides) for a given date range."
    args_schema = ListExceptionsArgs

    async def run(self, start_date: str, end_date: str, task_id: Optional[str] = None, **kwargs) -> Any:
        session: AsyncSession = kwargs.get("db_session")
        user_id: str = kwargs.get("user_id")
        if not session or not user_id:
            return {"success": False, "message": "Context error"}
        
        try:
            client = await get_lbs_client(user_id, session)
            excs = await client.get_exceptions(date.fromisoformat(start_date), date.fromisoformat(end_date))
            if task_id:
                excs = [e for e in excs if e.get("task_id") == task_id]
            
            return {"success": True, "message": f"Found {len(excs)} exceptions.", "data": {"exceptions": excs}}
        except Exception as e:
            return {"success": False, "message": f"Failed to list exceptions: {e}"}

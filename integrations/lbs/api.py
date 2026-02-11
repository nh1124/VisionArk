from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from datetime import date
from typing import List, Optional, Dict

from .client import LBSClient, TaskStatus
from domains.identity.auth import resolve_identity, Identity, bearer_scheme
from domains.identity.sync_coordinator import SyncCoordinator
from shared.database import get_async_db
from .models import LBSTaskExtension
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(tags=["LBS"])
ROUTER_PREFIX = "/lbs"


# Dependency to get LBS client with authenticated identity
async def get_lbs_client(
    identity: Identity = Depends(resolve_identity),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_async_db)
):
    """Get LBS client with user's registered LBS API key and remote user ID from ServiceRegistry"""
    from shared.database import ServiceRegistry
    from shared.encryption import decrypt_string
    from sqlalchemy import select
    
    # Try to get user's registered LBS service config
    lbs_api_key = None
    lbs_url = None
    
    result = await db.execute(select(ServiceRegistry).filter(
        ServiceRegistry.user_id == identity.user_id,
        ServiceRegistry.service_name == "lbs"
    ))
    service = result.scalars().first()
    
    if service:
        lbs_url = service.base_url
        # Decrypt API key
        if service.api_key_encrypted:
            try:
                lbs_api_key = decrypt_string(service.api_key_encrypted)
            except Exception:
                pass  # Fall back to env var logic in LBSClient if decryption fails
    
    # Use API key auth only
    return LBSClient(base_url=lbs_url, api_key=lbs_api_key)


# Pydantic models (kept for compatibility with frontend and Hub logic)
class TaskCreate(BaseModel):
    task_name: str
    context: str
    base_load_score: float
    rule_type: str
    due_date: Optional[date] = None
    mon: bool = False
    tue: bool = False
    wed: bool = False
    thu: bool = False
    fri: bool = False
    sat: bool = False
    sun: bool = False
    interval_days: Optional[int] = None
    anchor_date: Optional[date] = None
    month_day: Optional[int] = None
    nth_in_month: Optional[int] = None
    weekday_mon1: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None
    external_sync_id: Optional[str] = None
    is_locked: bool = False
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    meta_payload: Optional[Dict] = None


class TaskUpdate(BaseModel):
    task_name: Optional[str] = None
    context: Optional[str] = None
    base_load_score: Optional[float] = None
    active: Optional[bool] = None
    rule_type: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None
    mon: Optional[bool] = None
    tue: Optional[bool] = None
    wed: Optional[bool] = None
    thu: Optional[bool] = None
    fri: Optional[bool] = None
    sat: Optional[bool] = None
    sun: Optional[bool] = None
    interval_days: Optional[int] = None
    anchor_date: Optional[date] = None
    month_day: Optional[int] = None
    nth_in_month: Optional[int] = None
    weekday_mon1: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    external_sync_id: Optional[str] = None
    is_locked: Optional[bool] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    meta_payload: Optional[Dict] = None


class ExceptionCreate(BaseModel):
    task_id: str
    target_date: date
    exception_type: str 
    override_load_value: Optional[float] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    notes: Optional[str] = None
    is_locked: bool = False

class ExceptionUpdate(BaseModel):
    exception_type: Optional[str] = None
    override_load_value: Optional[float] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    notes: Optional[str] = None
    is_locked: Optional[bool] = None


# Proxy Endpoints
@router.get("/dashboard")
async def get_dashboard_data(
    start_date: Optional[date] = None,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return await client.get_dashboard(start_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks")
async def create_task(
    task: TaskCreate, 
    client: LBSClient = Depends(get_lbs_client),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        res = await client.create_task(task.model_dump(mode='json'))
        
        # Save extension metadata if provided
        task_data = task.model_dump()
        if "meta_payload" in task_data and task_data["meta_payload"] and "id" in res:
             ext = LBSTaskExtension(lbs_task_id=res["id"], meta_payload=task_data["meta_payload"])
             db.add(ext)
             await db.commit()

        # Trigger Export
        await SyncCoordinator.trigger_export(db, identity.user_id, reason="task creation")
        return res
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks")
async def list_tasks(
    context: Optional[str] = None,
    active: Optional[bool] = None,
    target_date: Optional[date] = None,
    lbs: LBSClient = Depends(get_lbs_client),
    db: AsyncSession = Depends(get_async_db)
):
    """
    List project tasks with optional filters.
    If target_date is provided, returns execution status for that day.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        # 1. Fetch task definitions
        all_tasks = await lbs.list_tasks(context=context, active=active)
        
        # 2. Optionally merge with schedule data for the target_date
        result = all_tasks
        if target_date:
            t_date_str = target_date.isoformat()
            schedule = await lbs.get_schedule(target_date, target_date)
            
            instance_map = {}
            if schedule and isinstance(schedule, list):
                for day in schedule:
                    if day.get("date") == t_date_str:
                        for t in day.get("tasks", []):
                            tid = str(t.get("task_id") or t.get("id"))
                            if tid:
                                instance_map[tid] = t

            filtered_tasks = []
            for task in all_tasks:
                tid = str(task.get("id") or task.get("task_id"))
                if tid in instance_map:
                    overlay = instance_map[tid]
                    # Merge status and metadata
                    if "load" in overlay: task["base_load_score"] = overlay["load"]
                    if "status" in overlay: task["status"] = overlay["status"]
                    if "start_time" in overlay: task["start_time"] = overlay["start_time"]
                    if "end_time" in overlay: task["end_time"] = overlay["end_time"]
                    if "is_locked" in overlay: task["is_locked"] = overlay["is_locked"]
                    task["due_date"] = t_date_str
                    # Standardize task_id for frontend
                    task["task_id"] = tid
                    filtered_tasks.append(task)
            result = filtered_tasks
        else:
            # Standardize task_id even when not merging
            for task in result:
                task["task_id"] = str(task.get("id") or task.get("task_id"))

        # 3. Merge VisionArk-specific extension data
        if result and isinstance(result, list):
            task_ids = [t.get("task_id") for t in result if t.get("task_id")]
            if task_ids:
                ext_res = await db.execute(select(LBSTaskExtension).filter(LBSTaskExtension.lbs_task_id.in_(task_ids)))
                ext_map = {e.lbs_task_id: e.meta_payload for e in ext_res.scalars().all()}
                
                for task in result:
                    task["meta_payload"] = ext_map.get(task.get("task_id"), {})

        return result
    except Exception as e:
        logger.exception(f"list_tasks failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/overdue")
async def get_overdue_tasks_api(
    client: LBSClient = Depends(get_lbs_client),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Look back 60 days and return tasks that were missed (status=todo).
    Merges with full task definitions and VisionArk extensions.
    """
    try:
        from datetime import timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=60)
        
        # 1. Fetch missed instances from schedule
        # The user confirmed get_schedule includes 'todo' status by default
        schedule = await client.get_schedule(start_date, end_date)
        
        missed_instances = []
        if schedule and isinstance(schedule, list):
            for day in schedule:
                d_str = day.get("date")
                # Overdue = past tasks. Today's tasks are NOT overdue yet.
                if d_str == end_date.isoformat():
                    continue
                    
                for t in day.get("tasks", []):
                    if t.get("status") == "todo":
                        t["due_date"] = d_str
                        missed_instances.append(t)
        
        if not missed_instances:
            return []
            
        # 2. Fetch all definitions to enrich data
        all_defs = await client.list_tasks()
        def_map = { str(d.get("task_id") or d.get("id")): d for d in all_defs }
        
        # 3. Fetch extensions
        task_ids = list(set([str(t.get("task_id") or t.get("id")) for t in missed_instances]))
        ext_res = await db.execute(select(LBSTaskExtension).filter(LBSTaskExtension.lbs_task_id.in_(task_ids)))
        ext_map = { e.lbs_task_id: e.meta_payload for e in ext_res.scalars().all() }
        
        # 4. Merge results
        overdue_tasks = []
        for instance in missed_instances:
            tid = str(instance.get("task_id") or instance.get("id"))
            definition = def_map.get(tid, {})
            
            # Combine: 1. Definition (base) 2. Instance (status/time) 3. Extension (VA meta)
            merged = {
                **definition,
                **instance,
                "task_id": tid,
                "meta_payload": ext_map.get(tid, {})
            }
            # Instance 'load' should map to 'base_load_score' in VA frontend
            if "load" in instance:
                merged["base_load_score"] = instance["load"]
            elif "base_load_score" not in merged and "load" in definition:
                merged["base_load_score"] = definition["load"]
                
            overdue_tasks.append(merged)
            
        return overdue_tasks
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"get_overdue_tasks failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task_details(
    task_id: str,
    target_date: Optional[date] = None,
    lbs: LBSClient = Depends(get_lbs_client),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get detailed information about a specific task.
    If target_date is provided, returns context-specific status for that date.
    """
    try:
        # 1. Fetch definition
        task = await lbs.get_task(task_id)
        
        # Ensure task has a consistent ID and basic fields to avoid frontend crashes
        task["task_id"] = str(task.get("id") or task.get("task_id") or task_id)
        task.setdefault("task_name", "Untitled Task")
        task.setdefault("context", "inbox")
        task.setdefault("status", "planned")
        task.setdefault("base_load_score", 1.0)
        
        # 2. Optionally merge with date-specific details
        if target_date:
            t_date_str = target_date.isoformat()
            schedule = await lbs.get_schedule(target_date, target_date)
            if schedule and isinstance(schedule, list):
                for day in schedule:
                    if day.get("date") == t_date_str:
                        # Robust matching using string conversion
                        overlay = next((t for t in day.get("tasks", []) if (str(t.get("task_id") or t.get("id")) == str(task_id))), None)
                        if overlay:
                            if "load" in overlay: task["base_load_score"] = overlay["load"]
                            if "status" in overlay: task["status"] = overlay["status"]
                            if "start_time" in overlay: task["start_time"] = overlay["start_time"]
                            if "end_time" in overlay: task["end_time"] = overlay["end_time"]
                            if "is_locked" in overlay: task["is_locked"] = overlay["is_locked"]
                            task["due_date"] = t_date_str
        
        # 3. Merge extension data
        ext = await db.get(LBSTaskExtension, task["task_id"])
        task["meta_payload"] = ext.meta_payload if ext else {}
            
        return task
    except Exception as e:
        import logging
        logging.getLogger(__name__).exception(f"get_task_details failed for {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}/resolved")
async def get_resolved_task(
    task_id: str,
    target_date: date,
    lbs: LBSClient = Depends(get_lbs_client)
):
    """Get a task instance merged with any date-specific exceptions."""
    try:
        return await lbs.get_resolved_task(task_id, target_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/tasks/{task_id}/history")
async def get_task_history(
    task_id: str,
    start_date: date,
    end_date: date,
    lbs: LBSClient = Depends(get_lbs_client)
):
    """Fetch execution history for a specific task."""
    try:
        return await lbs.get_task_history(task_id, start_date, end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}")
async def update_task(
    task_id: str, 
    task: TaskUpdate, 
    force_override: bool = Query(False),
    client: LBSClient = Depends(get_lbs_client),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        res = await client.update_task(task_id, task.model_dump(mode='json', exclude_unset=True), force_override=force_override)
        
        # Update extension metadata if provided
        task_data = task.model_dump(exclude_unset=True)
        if "meta_payload" in task_data and task_data["meta_payload"]:
             ext = await db.get(LBSTaskExtension, task_id)
             if ext:
                 ext.meta_payload = task_data["meta_payload"]
             else:
                 ext = LBSTaskExtension(lbs_task_id=task_id, meta_payload=task_data["meta_payload"])
                 db.add(ext)
             await db.commit()

        # Trigger Export
        await SyncCoordinator.trigger_export(db, identity.user_id, reason="task update")
        return res
    except Exception as e:
        await db.rollback()
        err_str = str(e)
        status_code = 500
        if len(err_str) >= 3 and err_str[:3].isdigit():
            status_code = int(err_str[:3])
            err_str = err_str[4:] if len(err_str) > 4 else err_str
        raise HTTPException(status_code=status_code, detail=err_str)


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str, 
    force_override: bool = Query(False),
    client: LBSClient = Depends(get_lbs_client),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        res = await client.delete_task(task_id, force_override=force_override)
        # Trigger Export
        await SyncCoordinator.trigger_export(db, identity.user_id, reason="task deletion")
        return res
    except Exception as e:
        err_str = str(e)
        status_code = 500
        if len(err_str) >= 3 and err_str[:3].isdigit():
            status_code = int(err_str[:3])
            err_str = err_str[4:] if len(err_str) > 4 else err_str
        raise HTTPException(status_code=status_code, detail=err_str)


@router.post("/tasks/upload-csv")
async def upload_tasks_csv(
    file: UploadFile = File(...),
    client: LBSClient = Depends(get_lbs_client)
):
    """Proxy CSV upload to LBS microservice for server-side task creation"""
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed")
    
    try:
        content = await file.read()
        return await client.upload_tasks_csv(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TaskBulkDelete(BaseModel):
    task_ids: List[str]


class TaskBulkActiveUpdate(BaseModel):
    task_ids: List[str]
    active: bool


@router.post("/tasks/bulk-delete")
async def bulk_delete_tasks(bulk_in: TaskBulkDelete, client: LBSClient = Depends(get_lbs_client)):
    try:
        return await client.bulk_delete_tasks(bulk_in.task_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/bulk-update-active")
async def bulk_update_active(bulk_in: TaskBulkActiveUpdate, client: LBSClient = Depends(get_lbs_client)):
    try:
        return await client.bulk_update_active(bulk_in.task_ids, bulk_in.active)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exceptions")
async def create_exception(exc: ExceptionCreate, force_override: bool = Query(True), client: LBSClient = Depends(get_lbs_client)):
    try:
        return await client.create_exception(exc.model_dump(mode='json'), force_override=force_override)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/exceptions/{exception_id}")
async def update_exception(exception_id: int, exc: ExceptionUpdate, force_override: bool = Query(True), client: LBSClient = Depends(get_lbs_client)):
    try:
        return await client.update_exception(exception_id, exc.model_dump(mode='json', exclude_unset=True), force_override=force_override)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/exceptions/{exception_id}")
async def delete_exception(exception_id: int, force_override: bool = Query(True), client: LBSClient = Depends(get_lbs_client)):
    try:
        return await client.delete_exception(exception_id, force_override=force_override)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calculate/{target_date}")
async def calculate_load(
    target_date: date,
    status: Optional[List[str]] = Query(None),
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return await client.calculate_load(target_date, statuses=status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/heatmap")
async def get_heatmap(
    start: date,
    end: date,
    include_completed: bool = True,
    status: Optional[List[str]] = Query(None),
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        if status:
            return await client.get_heatmap(start, end, statuses=status)
        
        # Backward compatibility for include_completed
        statuses = [TaskStatus.DONE, TaskStatus.TODO] if include_completed else [TaskStatus.TODO]
        return await client.get_heatmap(start, end, statuses=statuses)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trends")
async def get_trends(
    weeks: int = 12,
    start_date: Optional[date] = None,
    status: Optional[List[str]] = Query(None),
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return await client.get_trends(weeks, start_date, statuses=status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/context-distribution")
async def get_context_distribution(
    start: date,
    end: date,
    status: Optional[List[str]] = Query(None),
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return await client.get_context_distribution(start, end, statuses=status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule")
async def get_schedule(
    start_date: date,
    end_date: date,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return await client.get_schedule(start_date, end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/expand")
async def expand_tasks(
    start_date: date,
    end_date: date,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return await client.force_expand(start_date, end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TaskCompletionRequest(BaseModel):
    target_date: date
    status: str = "done"


@router.post("/tasks/{task_id}/complete")
async def complete_task(
    task_id: str,
    req: TaskCompletionRequest,
    client: LBSClient = Depends(get_lbs_client),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    import logging
    import traceback
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"Completing task {task_id} for date {req.target_date} with status {req.status}")
        res = await client.toggle_task_completion(task_id, req.target_date, req.status)
        
        # Trigger Export
        try:
            await SyncCoordinator.trigger_export(db, identity.user_id, reason="task completion update")
        except Exception as export_err:
            logger.error(f"Sync export failed but task was updated: {export_err}")
            # We don't fail the whole request if export fails, but let's log it
            
        return res
    except Exception as e:
        logger.error(f"Error in complete_task: {e}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

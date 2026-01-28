from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from datetime import date
from typing import List, Optional, Dict

from .client import LBSClient, TaskStatus
from services.auth import resolve_identity, Identity, bearer_scheme
from services.sync_coordinator import SyncCoordinator
from models.database import get_async_db
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
    from models.database import ServiceRegistry
    from utils.encryption import decrypt_string
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
    notes: Optional[str] = None


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
        logger.info(f"list_tasks called: context={context}, active={active}, target_date={target_date}")
        result = await lbs.list_tasks(context=context, active=active, target_date=target_date)
        
        # Merge extension data
        if result and isinstance(result, list):
            task_ids = [t["id"] for t in result if "id" in t]
            if task_ids:
                ext_res = await db.execute(select(LBSTaskExtension).filter(LBSTaskExtension.lbs_task_id.in_(task_ids)))
                ext_map = {e.lbs_task_id: e.meta_payload for e in ext_res.scalars().all()}
                
                for task in result:
                    if task["id"] in ext_map:
                        task["meta_payload"] = ext_map[task["id"]]
                    else:
                        task["meta_payload"] = {}

        logger.info(f"list_tasks returning {len(result)} tasks")
        return result
    except Exception as e:
        logger.exception(f"list_tasks failed: {e}")
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
        res = await lbs.get_task(task_id, target_date=target_date)
        
        # Merge extension data
        ext = await db.get(LBSTaskExtension, task_id)
        if ext:
            res["meta_payload"] = ext.meta_payload
        else:
            res["meta_payload"] = {}
            
        return res
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
    client: LBSClient = Depends(get_lbs_client),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        res = await client.update_task(task_id, task.model_dump(mode='json', exclude_unset=True))
        
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
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}")
async def delete_task(
    task_id: str, 
    client: LBSClient = Depends(get_lbs_client),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    try:
        res = await client.delete_task(task_id)
        # Trigger Export
        await SyncCoordinator.trigger_export(db, identity.user_id, reason="task deletion")
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
async def create_exception(exc: ExceptionCreate, client: LBSClient = Depends(get_lbs_client)):
    try:
        return await client.create_exception(exc.model_dump(mode='json'))
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

from fastapi import APIRouter, Depends, HTTPException, Header, UploadFile, File
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from datetime import date
from typing import List, Optional, Dict

from services.lbs_client import LBSClient
from services.auth import resolve_identity, Identity, bearer_scheme, get_db
from sqlalchemy.orm import Session

router = APIRouter(prefix="/api/lbs", tags=["LBS"])


# Dependency to get LBS client with authenticated identity
def get_lbs_client(
    identity: Identity = Depends(resolve_identity),
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db)
):
    """Get LBS client with user's registered LBS API key and remote user ID from ServiceRegistry"""
    from models.database import ServiceRegistry
    from utils.encryption import decrypt_string
    
    # Try to get user's registered LBS service config
    lbs_api_key = None
    lbs_url = None
    
    service = db.query(ServiceRegistry).filter(
        ServiceRegistry.user_id == identity.user_id,
        ServiceRegistry.service_name == "lbs"
    ).first()
    
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


class ExceptionCreate(BaseModel):
    task_id: str
    target_date: date
    exception_type: str 
    override_load_value: Optional[float] = None
    notes: Optional[str] = None


# Proxy Endpoints
@router.get("/dashboard")
def get_dashboard_data(
    start_date: Optional[date] = None,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return client.get_dashboard(start_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks")
def create_task(task: TaskCreate, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.create_task(task.model_dump(mode='json'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks")
async def list_tasks(
    context: Optional[str] = None,
    active: Optional[bool] = None,
    target_date: Optional[date] = None,
    lbs: LBSClient = Depends(get_lbs_client)
):
    """
    List project tasks with optional filters.
    If target_date is provided, returns execution status for that day.
    """
    import logging
    logger = logging.getLogger(__name__)
    try:
        logger.info(f"list_tasks called: context={context}, active={active}, target_date={target_date}")
        result = lbs.get_tasks(context=context, active=active, target_date=target_date)
        logger.info(f"list_tasks returning {len(result)} tasks")
        return result
    except Exception as e:
        logger.exception(f"list_tasks failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks/{task_id}")
async def get_task_details(
    task_id: str,
    target_date: Optional[date] = None,
    lbs: LBSClient = Depends(get_lbs_client)
):
    """
    Get detailed information about a specific task.
    If target_date is provided, returns context-specific status for that date.
    """
    try:
        return lbs.get_task(task_id, target_date=target_date)
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
        return lbs.get_task_history(task_id, start_date, end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}")
def update_task(task_id: str, task: TaskUpdate, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.update_task(task_id, task.model_dump(mode='json', exclude_unset=True))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.delete_task(task_id)
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
        return client.upload_tasks_csv(content, file.filename)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TaskBulkDelete(BaseModel):
    task_ids: List[str]


class TaskBulkActiveUpdate(BaseModel):
    task_ids: List[str]
    active: bool


@router.post("/tasks/bulk-delete")
def bulk_delete_tasks(bulk_in: TaskBulkDelete, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.bulk_delete_tasks(bulk_in.task_ids)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks/bulk-update-active")
def bulk_update_active(bulk_in: TaskBulkActiveUpdate, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.bulk_update_active(bulk_in.task_ids, bulk_in.active)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exceptions")
def create_exception(exc: ExceptionCreate, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.create_exception(exc.model_dump(mode='json'))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/calculate/{target_date}")
def calculate_load(target_date: date, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.calculate_load(target_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/heatmap")
def get_heatmap(
    start: date,
    end: date,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return client.get_heatmap(start, end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/trends")
def get_trends(
    weeks: int = 12,
    start_date: Optional[date] = None,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return client.get_trends(weeks, start_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/context-distribution")
def get_context_distribution(
    start: date,
    end: date,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return client.get_context_distribution(start, end)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/schedule")
def get_schedule(
    start_date: date,
    end_date: date,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return client.get_schedule(start_date, end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/expand")
def expand_tasks(
    start_date: date,
    end_date: date,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return client.force_expand(start_date, end_date)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TaskCompletionRequest(BaseModel):
    target_date: date
    status: str = "done"


@router.post("/tasks/{task_id}/complete")
def complete_task(
    task_id: str,
    req: TaskCompletionRequest,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        from services.lbs_client import TaskStatus
        status_val = req.status
        return client.toggle_task_completion(task_id, req.target_date, status_val)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

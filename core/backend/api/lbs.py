from fastapi import APIRouter, Depends, HTTPException, Header
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
    lbs_user_id = identity.user_id  # Default to OS user ID
    
    service = db.query(ServiceRegistry).filter(
        ServiceRegistry.user_id == identity.user_id,
        ServiceRegistry.service_name == "lbs"
    ).first()
    
    if service:
        # Use remote_user_id if configured (for cross-service user mapping)
        if service.remote_user_id:
            lbs_user_id = service.remote_user_id
        
        # Decrypt API key
        if service.api_key_encrypted:
            try:
                lbs_api_key = decrypt_string(service.api_key_encrypted)
            except Exception:
                pass  # Fall back to env var if decryption fails
    
    # Use API key auth and mapped user ID for LBS communication
    return LBSClient(user_id=lbs_user_id, api_key=lbs_api_key)


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
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    notes: Optional[str] = None


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
    start_date: Optional[date] = None
    end_date: Optional[date] = None


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
        return client.create_task(task.model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/tasks")
def list_tasks(
    context: Optional[str] = None,
    client: LBSClient = Depends(get_lbs_client)
):
    try:
        return client.get_tasks(context)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/tasks/{task_id}")
def update_task(task_id: str, task: TaskUpdate, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.update_task(task_id, task.model_dump(exclude_unset=True))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.delete_task(task_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/exceptions")
def create_exception(exc: ExceptionCreate, client: LBSClient = Depends(get_lbs_client)):
    try:
        return client.create_exception(exc.model_dump())
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

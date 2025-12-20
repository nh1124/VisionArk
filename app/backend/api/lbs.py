from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from datetime import date
from typing import List, Optional, Dict

from services.lbs_client import LBSClient
from services.auth import resolve_identity, Identity

router = APIRouter(prefix="/api/lbs", tags=["LBS"])


# Dependency to get LBS client with authenticated identity
def get_lbs_client(identity: Identity = Depends(resolve_identity)):
    """Get LBS client with user_id from authenticated identity"""
    return LBSClient(user_id=identity.user_id)


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

"""
Automation & Scheduled Tasks API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete

from services.auth import resolve_identity, Identity
from models.database import get_async_db, ScheduledTask, ScheduledTaskStatus
from services.aes_dispatcher import AESDispatcher

router = APIRouter(prefix="/api/automation", tags=["Automation"])

class ScheduleTaskRequest(BaseModel):
    project_id: str
    task_type: str
    scheduled_at: datetime
    payload: Dict[str, Any] = Field(default_factory=dict)
    recurring_rule: Optional[str] = None

class ScheduledTaskSchema(BaseModel):
    id: str
    project_id: Optional[str]
    task_type: str
    payload: Dict[str, Any]
    scheduled_at: datetime
    recurring_rule: Optional[str]
    status: str
    last_run_at: Optional[datetime]
    created_at: datetime

@router.get("/tasks", response_model=List[ScheduledTaskSchema])
async def list_scheduled_tasks(
    project_id: Optional[str] = None,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List scheduled tasks for the user/project"""
    stmt = select(ScheduledTask).filter(ScheduledTask.user_id == identity.user_id)
    if project_id:
        stmt = stmt.filter(ScheduledTask.project_id == project_id)
    
    stmt = stmt.order_by(ScheduledTask.scheduled_at.desc())
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    
    return [
        ScheduledTaskSchema(
            id=t.id,
            project_id=t.project_id,
            task_type=t.task_type,
            payload=t.payload,
            scheduled_at=t.scheduled_at,
            recurring_rule=t.recurring_rule,
            status=t.status,
            last_run_at=t.last_run_at,
            created_at=t.created_at
        )
        for t in tasks
    ]

@router.post("/schedule")
async def schedule_task(
    request: ScheduleTaskRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Schedule a new automated task"""
    from models.database import AsyncSessionLocal
    dispatcher = AESDispatcher(AsyncSessionLocal)
    
    task_id = await dispatcher.schedule_task(
        user_id=identity.user_id,
        task_type=request.task_type,
        scheduled_at=request.scheduled_at,
        project_id=request.project_id,
        payload=request.payload,
        recurring_rule=request.recurring_rule
    )
    
    return {"status": "success", "task_id": task_id}

@router.delete("/tasks/{task_id}")
async def cancel_task(
    task_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Cancel/Delete a scheduled task"""
    stmt = select(ScheduledTask).filter(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == identity.user_id
    )
    result = await db.execute(stmt)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    await db.delete(task)
    await db.commit()
    
    return {"status": "success", "message": "Task cancelled"}

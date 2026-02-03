"""
Automation & Scheduled Tasks API
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete as sql_delete
from sqlalchemy.orm import joinedload

from services.auth import resolve_identity, Identity
from services.aes_dispatcher import AESDispatcher
import uuid
from models.database import get_async_db, ScheduledTask, ScheduledTaskStatus

router = APIRouter(prefix="/api/automation", tags=["Automation"])

class ScheduleTaskRequest(BaseModel):
    project_id: Optional[str] = None
    task_type: str
    scheduled_at: datetime
    payload: Dict[str, Any] = Field(default_factory=dict)
    recurring_rule: Optional[str] = None

class ScheduledTaskSchema(BaseModel):
    id: str
    project_id: Optional[str]
    project_name: Optional[str] = None
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
    exclude_system: bool = False,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """List scheduled tasks for the user/project"""
    print(f"[API] Listing tasks. exclude_system={exclude_system}")
    
    stmt = select(ScheduledTask).options(
        joinedload(ScheduledTask.project)
    ).filter(ScheduledTask.user_id == identity.user_id)
    
    if project_id:
        stmt = stmt.filter(ScheduledTask.project_id == project_id)
    
    if exclude_system:
        system_types = [
            "HARD_DELETE", 
            "SYNC_PROJECT_FILES", 
            "PROJECT_SNAPSHOT", 
            "SYSTEM_SKILL_MINING",
            "SYNC_ROUTER_HOOKS",
            "SYSTEM_TIMER"
        ]
        stmt = stmt.filter(ScheduledTask.task_type.notin_(system_types))

    stmt = stmt.order_by(ScheduledTask.scheduled_at.desc())
    result = await db.execute(stmt)
    tasks = result.scalars().unique().all()
    
    return [
        ScheduledTaskSchema(
            id=t.id,
            project_id=t.project_id,
            project_name=t.project.name if t.project else None,
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
    
    # Handle timezone
    dt = request.scheduled_at
    if dt.tzinfo is not None:
        import datetime as datetime_mod
        if dt.tzinfo != datetime_mod.timezone.utc:
            dt = dt.astimezone(datetime_mod.timezone.utc)
        dt = dt.replace(tzinfo=None) # Store as naive UTC

    # Validation: project_id exists if provided
    if request.project_id:
        from models.database import Project
        res = await db.execute(select(Project).filter(Project.id == request.project_id))
        if not res.scalars().first():
            raise HTTPException(status_code=400, detail=f"Project {request.project_id} not found")

    new_task = ScheduledTask(
        id=str(uuid.uuid4()),
        user_id=identity.user_id,
        project_id=request.project_id,
        task_type=request.task_type,
        payload=request.payload,
        scheduled_at=dt,
        recurring_rule=request.recurring_rule,
        status=ScheduledTaskStatus.PENDING
    )
    db.add(new_task)
    await db.commit()
    
    print(f"[API] Manual schedule: {new_task.id} for {dt}")
    
    return {"status": "success", "task_id": new_task.id}

@router.put("/tasks/{task_id}")
async def update_task(
    task_id: str,
    request: ScheduleTaskRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Update an existing scheduled task"""
    stmt = select(ScheduledTask).filter(
        ScheduledTask.id == task_id,
        ScheduledTask.user_id == identity.user_id
    )
    result = await db.execute(stmt)
    task = result.scalars().first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
        
    if task.project_id != request.project_id and request.project_id:
        from models.database import Project
        res = await db.execute(select(Project).filter(Project.id == request.project_id))
        if not res.scalars().first():
            raise HTTPException(status_code=400, detail=f"Project {request.project_id} not found")

    # Update fields
    task.project_id = request.project_id
    # task_type usually shouldn't change, but we allow it if payload matches
    task.task_type = request.task_type 
    task.payload = request.payload
    task.scheduled_at = request.scheduled_at.replace(tzinfo=None) # Ensure naive
    task.recurring_rule = request.recurring_rule
    
    # Reset status to pending if it was failed/completed, so it runs again at new time?
    # Or just leave it? Usually if you edit a future task it is pending. 
    # If editing a past task to run again, status should be pending.
    task.status = ScheduledTaskStatus.PENDING
    
    await db.commit()
    
    return {"status": "success", "message": "Task updated"}

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

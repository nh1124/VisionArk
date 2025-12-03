"""
LBS API endpoints
Dashboard data, task CRUD, and load calculations
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import date, datetime, timedelta
from typing import List, Optional
import uuid

from models.database import get_session, get_engine, Task, TaskException, RuleType
from services.lbs_engine import LBSEngine

router = APIRouter(prefix="/api/lbs", tags=["LBS"])

# Dependency to get DB session
def get_db():
    engine = get_engine()  # Use automatic path detection
    session = get_session(engine)
    try:
        yield session
    finally:
        session.close()


# Pydantic models for requests/responses
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
    # Weekly recurrence fields
    mon: Optional[bool] = None
    tue: Optional[bool] = None
    wed: Optional[bool] = None
    thu: Optional[bool] = None
    fri: Optional[bool] = None
    sat: Optional[bool] = None
    sun: Optional[bool] = None
    # Other recurrence fields
    interval_days: Optional[int] = None
    anchor_date: Optional[date] = None
    month_day: Optional[int] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None


class ExceptionCreate(BaseModel):
    task_id: str
    target_date: date
    exception_type: str  # SKIP, OVERRIDE_LOAD, FORCE_DO
    override_load_value: Optional[float] = None
    notes: Optional[str] = None


# Endpoints
@router.get("/dashboard")
def get_dashboard_data(
    start_date: Optional[date] = None,
    db: Session = Depends(get_db)
):
    """
    Get dashboard data for LBS visualization
    Default: current week
    """
    if not start_date:
        start_date = date.today() - timedelta(days=date.today().weekday())  # Monday
    
    engine = LBSEngine(db)
    
    # Get weekly stats
    weekly = engine.get_weekly_stats(start_date)
    
    # Get today's data
    today = engine.calculate_daily_load(date.today())
    
    # Get daily breakdown for the week
    daily_data = []
    current = start_date
    for i in range(7):
        daily = engine.calculate_daily_load(current)
        daily_data.append(daily)
        current += timedelta(days=1)
    
    
    # Calculate consecutive overload days (for analytics)
    # Use the month of start_date
    cap = engine.config.get("CAP", 8.0)
    max_consecutive = 0
    current_consecutive = 0
    
    # Calculate for the month containing start_date
    from calendar import monthrange
    year = start_date.year
    month = start_date.month
    _, last_day = monthrange(year, month)
    
    month_start = date(year, month, 1)
    month_end = date(year, month, last_day)
    
    check_date = month_start
    while check_date <= month_end:
        daily_load_data = engine.calculate_daily_load(check_date)
        if daily_load_data["adjusted_load"] > cap:
            current_consecutive += 1
            max_consecutive = max(max_consecutive, current_consecutive)
        else:
            current_consecutive = 0
        check_date += timedelta(days=1)
    
    return {
        "today": today,
        "weekly": weekly,
        "daily_breakdown": daily_data,
        "config": engine.config,
        # Analytics stats
        "weekly_avg_load": weekly["average_load"],
        "overload_consecutive_days": max_consecutive,
        "recovery_day_percentage": weekly["recovery_rate"]
    }


@router.post("/tasks")
def create_task(task: TaskCreate, db: Session = Depends(get_db)):
    """Create a new task"""
    # Log the incoming due_date for debugging
    print(f"[CREATE TASK] Received due_date: {task.due_date} (type: {type(task.due_date)})")
    
    new_task = Task(
        task_id=f"T-{uuid.uuid4().hex[:8]}",
        task_name=task.task_name,
        context=task.context,
        base_load_score=task.base_load_score,
        rule_type=task.rule_type,
        due_date=task.due_date,
        mon=task.mon,
        tue=task.tue,
        wed=task.wed,
        thu=task.thu,
        fri=task.fri,
        sat=task.sat,
        sun=task.sun,
        interval_days=task.interval_days,
        anchor_date=task.anchor_date,
        start_date=task.start_date,
        end_date=task.end_date,
        notes=task.notes,
        active=True
    )
    
    db.add(new_task)
    db.commit()
    db.refresh(new_task)
    
    # Log what was actually stored
    print(f"[CREATE TASK] Stored in DB - task_id: {new_task.task_id}, due_date: {new_task.due_date}")
    
    # Expand tasks using the task's date range (with defaults)
    engine = LBSEngine(db)
    if new_task.start_date:
        expand_start = new_task.start_date
    elif new_task.due_date:
        expand_start = new_task.due_date
    else:
        expand_start = date.today()
    
    if new_task.end_date:
        expand_end = new_task.end_date
    elif new_task.due_date:
        expand_end = new_task.due_date
    else:
        expand_end = date.today() + timedelta(days=90)
    
    engine.expand_tasks(expand_start, expand_end)
    
    return {"task_id": new_task.task_id, "message": "Task created successfully"}


@router.put("/tasks/{task_id}")
def update_task(task_id: str, task: TaskUpdate, db: Session = Depends(get_db)):
    """Update an existing task"""
    db_task = db.query(Task).filter(Task.task_id == task_id).first()
    if not db_task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Update basic fields
    if task.task_name is not None:
        db_task.task_name = task.task_name
    if task.context is not None:
        db_task.context = task.context
    if task.base_load_score is not None:
        db_task.base_load_score = task.base_load_score
    if task.active is not None:
        db_task.active = task.active
    if task.rule_type is not None:
        db_task.rule_type = task.rule_type
    if task.notes is not None:
        db_task.notes = task.notes
    
    # Update rule-specific fields
    if task.due_date is not None:
        db_task.due_date = task.due_date
    
    # Update weekly recurrence fields
    if task.mon is not None:
        db_task.mon = task.mon
    if task.tue is not None:
        db_task.tue = task.tue
    if task.wed is not None:
        db_task.wed = task.wed
    if task.thu is not None:
        db_task.thu = task.thu
    if task.fri is not None:
        db_task.fri = task.fri
    if task.sat is not None:
        db_task.sat = task.sat
    if task.sun is not None:
        db_task.sun = task.sun
    
    # Update other recurrence fields
    if task.interval_days is not None:
        db_task.interval_days = task.interval_days
    if task.anchor_date is not None:
        db_task.anchor_date = task.anchor_date
    if task.month_day is not None:
        db_task.month_day = task.month_day
    if task.start_date is not None:
        db_task.start_date = task.start_date
    if task.end_date is not None:
        db_task.end_date = task.end_date
    
    db_task.updated_at = datetime.utcnow()
    db.commit()
    
    # Re-expand tasks using the task's date range (with defaults)
    engine = LBSEngine(db)
    if db_task.start_date:
        expand_start = db_task.start_date
    elif db_task.due_date:
        expand_start = db_task.due_date
    else:
        expand_start = date.today()
    
    if db_task.end_date:
        expand_end = db_task.end_date
    elif db_task.due_date:
        expand_end = db_task.due_date
    else:
        expand_end = date.today() + timedelta(days=90)
    
    engine.expand_tasks(expand_start, expand_end)
    
    return {"message": "Task updated successfully"}


@router.get("/tasks")
def list_tasks(
    context: Optional[str] = None,
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """List all tasks, optionally filtered by context"""
    query = db.query(Task)
    
    if active_only:
        query = query.filter(Task.active == True)
    if context:
        query = query.filter(Task.context == context)
    
    tasks = query.all()
    return [
        {
            "task_id": t.task_id,
            "task_name": t.task_name,
            "context": t.context,
            "base_load_score": t.base_load_score,
            "rule_type": t.rule_type,
            "active": t.active
        }
        for t in tasks
    ]


@router.post("/exceptions")
def create_exception(exc: ExceptionCreate, db: Session = Depends(get_db)):
    """Add a task exception"""
    new_exc = TaskException(
        task_id=exc.task_id,
        target_date=exc.target_date,
        exception_type=exc.exception_type,
        override_load_value=exc.override_load_value,
        notes=exc.notes
    )
    
    db.add(new_exc)
    db.commit()
    
    # Re-expand affected date range
    engine = LBSEngine(db)
    engine.expand_tasks(exc.target_date, exc.target_date)
    
    return {"message": "Exception created successfully"}


@router.get("/calculate/{target_date}")
def calculate_load(target_date: date, db: Session = Depends(get_db)):
    """Calculate load for a specific date"""
    engine = LBSEngine(db)
    return engine.calculate_daily_load(target_date)


@router.post("/expand")
def expand_tasks(
    start_date: date,
    end_date: date,
    db: Session = Depends(get_db)
):
    """Manually trigger task expansion"""
    engine = LBSEngine(db)
    engine.expand_tasks(start_date, end_date)
    return {"message": f"Tasks expanded from {start_date} to {end_date}"}


# Advanced Visualization Endpoints
@router.get("/heatmap")
async def get_heatmap_data(
    start: str,  # YYYY-MM-DD
    end: str,    # YYYY-MM-DD
    db: Session = Depends(get_db)
):
    """Get heat map data for calendar visualization"""
    from services.lbs_engine import LBSEngine
    
    engine = LBSEngine(db)
    start_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    
    days_data = []
    current_date = start_date
    
    while current_date <= end_date:
        date_str = current_date.strftime("%Y-%m-%d")
        daily_load = engine.calculate_daily_load(date_str)
        
        load = daily_load.get("adjusted_load", 0)
        if load < 6.0:
            level = "SAFE"
        elif load < 8.0:
            level = "WARNING"
        elif load <= 10.0:
            level = "DANGER"
        else:
            level = "CRITICAL"
        
        days_data.append({
            "date": date_str,
            "load": load,
            "level": level,
            "taskCount": daily_load.get("task_count", 0)
        })
        
        current_date += timedelta(days=1)
    
    return {"days": days_data}


@router.get("/trends")
async def get_trend_data(
    weeks: int = 12,
    db: Session = Depends(get_db)
):
    """Get trend analysis data for the specified number of weeks"""
    from services.lbs_engine import LBSEngine
    
    engine = LBSEngine(db)
    end_date = datetime.now().date()
    start_date = end_date - timedelta(weeks=weeks)
    
    trend_data = []
    current_week_start = start_date
    
    while current_week_start < end_date:
        week_end = current_week_start + timedelta(days=6)
        
        week_loads = []
        current_day = current_week_start
        while current_day <= week_end and current_day <= end_date:
            date_str = current_day.strftime("%Y-%m-%d")
            daily_load = engine.calculate_daily_load(date_str)
            week_loads.append(daily_load.get("adjusted_load", 0))
            current_day += timedelta(days=1)
        
        if week_loads:
            trend_data.append({
                "date": current_week_start.strftime("%Y-%m-%d"),
                "average_load": sum(week_loads) / len(week_loads),
                "max_load": max(week_loads),
                "min_load": min(week_loads)
            })
        
        current_week_start = week_end + timedelta(days=1)
    
    return {"trends": trend_data}


@router.get("/context-distribution")
async def get_context_distribution(
    start: str,
    end: str,
    db: Session = Depends(get_db)
):
    """Get context (Spoke) load distribution for stacked bar chart"""
    from sqlalchemy import text
    
    query = text("""
        SELECT 
            c.target_date,
            t.context,
            SUM(c.calculated_load) as total_load
        FROM lbs_daily_cache c
        JOIN tasks t ON c.task_id = t.task_id
        WHERE c.target_date BETWEEN :start AND :end
        GROUP BY c.target_date, t.context
        ORDER BY c.target_date, t.context
    """)
    
    result = db.execute(query, {"start": start, "end": end})
    
    distribution_data = {}
    for row in result:
        date_str = row[0] if isinstance(row[0], str) else row[0].strftime("%Y-%m-%d")
        context = row[1] or "unassigned"
        load = float(row[2])
        
        if date_str not in distribution_data:
            distribution_data[date_str] = {
                "date": date_str,
                "total_load": 0,
                "contexts": []
            }
        
        distribution_data[date_str]["total_load"] += load
        distribution_data[date_str]["contexts"].append({
            "context": context,
            "load": load,
            "color": "#3b82f6"
        })
    
    return {"distribution": list(distribution_data.values())}



# ============================================================================
# TASK MANAGEMENT ENDPOINTS (for Notion-style UI)
# ============================================================================

@router.get("/tasks/list")
def get_task_list(
    spoke: Optional[str] = None,
    status: Optional[str] = None,  # "active" or "completed"
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db)
):
    """Get filtered and paginated task list"""
    query = db.query(Task)
    
    # Filter by spoke (context)
    if spoke:
        query = query.filter(Task.context == spoke)
    
    # Filter by status
    if status == "active":
        query = query.filter(Task.active == True)
    elif status == "completed":
        query = query.filter(Task.active == False)
    
    # Order by due date (nulls last) and name
    query = query.order_by(Task.due_date.asc().nullslast(), Task.task_name)
    
    # Paginate
    total = query.count()
    tasks = query.offset(offset).limit(limit).all()
    
    return {
        "tasks": [{
            "task_id": t.task_id,
            "task_name": t.task_name,
            "context": t.context,
            "base_load_score": t.base_load_score,
            "active": t.active,
            "rule_type": t.rule_type,
            "due_date": str(t.due_date) if t.due_date else None,
            "start_date": str(t.start_date) if t.start_date else None,
            "end_date": str(t.end_date) if t.end_date else None,
            "notes": t.notes,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        } for t in tasks],
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.get("/tasks/{task_id}")
def get_task_detail(task_id: str, db: Session = Depends(get_db)):
    """Get detailed task information"""
    task = db.query(Task).filter(Task.task_id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return {
        "task_id": task.task_id,
        "task_name": task.task_name,
        "context": task.context,
        "base_load_score": task.base_load_score,
        "active": task.active,
        "rule_type": task.rule_type,
        "due_date": str(task.due_date) if task.due_date else None,
        "mon": task.mon,
        "tue": task.tue,
        "wed": task.wed,
        "thu": task.thu,
        "fri": task.fri,
        "sat": task.sat,
        "sun": task.sun,
        "interval_days": task.interval_days,
        "anchor_date": str(task.anchor_date) if task.anchor_date else None,
        "start_date": str(task.start_date) if task.start_date else None,
        "end_date": str(task.end_date) if task.end_date else None,
        "notes": task.notes,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.get("/tasks/by-date/{target_date}")
def get_tasks_by_date(target_date: str, db: Session = Depends(get_db)):
    """Get all tasks scheduled for a specific date"""
    try:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    engine = LBSEngine(db)
    tasks_for_day = engine.get_tasks_for_date(date_obj)
    
    return {
        "date": target_date,
        "tasks": [{
            "task_id": t.task_id,
            "task_name": t.task_name,
            "context": t.context,
            "base_load_score": t.base_load_score,
            "active": t.active,
            "notes": t.notes,
        } for t in tasks_for_day]
    }


@router.get("/calendar-data")
def get_calendar_data(
    start: str,
    end: str,
    db: Session = Depends(get_db)
):
    """Get task counts by date for calendar visualization"""
    try:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
    
    engine = LBSEngine(db)
    calendar_data = {}
    
    current_date = start_date
    while current_date <= end_date:
        tasks = engine.get_tasks_for_date(current_date)
        
        # Group by spoke (context) for colored dots
        spoke_counts = {}
        for task in tasks:
            spoke_counts[task.context] = spoke_counts.get(task.context, 0) + 1
        
        calendar_data[str(current_date)] = {
            "total": len(tasks),
            "by_spoke": spoke_counts
        }
        
        current_date += timedelta(days=1)
    
    return calendar_data


class BulkDeleteRequest(BaseModel):
    task_ids: List[str]

@router.post("/tasks/bulk-delete")
def bulk_delete_tasks(request: BulkDeleteRequest, db: Session = Depends(get_db)):
    """Delete multiple tasks at once"""
    deleted_count = 0
    
    for task_id in request.task_ids:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if task:
            db.delete(task)
            deleted_count += 1
    
    db.commit()
    
    # Re-expand cache after bulk deletion
    engine = LBSEngine(db)
    engine.expand_tasks(date.today(), date.today() + timedelta(days=90))
    
    return {
        "message": f"Deleted {deleted_count} tasks",
        "deleted_count": deleted_count
    }


class BulkUpdateStatusRequest(BaseModel):
    task_ids: List[str]
    active: bool

@router.post("/tasks/bulk-update-status")
def bulk_update_status(request: BulkUpdateStatusRequest, db: Session = Depends(get_db)):
    """Update active status for multiple tasks"""
    updated_count = 0
    
    for task_id in request.task_ids:
        task = db.query(Task).filter(Task.task_id == task_id).first()
        if task:
            task.active = request.active
            task.updated_at = datetime.utcnow()
            updated_count += 1
    
    db.commit()
    
    # Re-expand cache after status changes
    engine = LBSEngine(db)
    engine.expand_tasks(date.today(), date.today() + timedelta(days=90))
    
    return {
        "message": f"Updated {updated_count} tasks",
        "updated_count": updated_count
    }

@router.delete("/tasks/{task_id}")
def delete_task(task_id: str, db: Session = Depends(get_db)):
    """Delete a single task"""
    task = db.query(Task).filter(Task.task_id == task_id).first()
    
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    db.delete(task)
    db.commit()
    
    # Re-expand cache after deletion
    engine = LBSEngine(db)
    engine.expand_tasks(date.today(), date.today() + timedelta(days=90))
    
    return {"message": f"Task {task_id} deleted successfully"}

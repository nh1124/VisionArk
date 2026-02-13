"""
Hub Suggestions API
Provides proactive suggestions based on task status, spoke activity, and workload
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime, date, timedelta
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from shared.database import get_async_db, Project
from integrations.lbs import LBSClient, get_lbs_client
from api.auth import get_current_user

router = APIRouter(prefix="/api/hub/suggestions", tags=["suggestions"])


class HubSuggestion(BaseModel):
    id: str
    type: str  # 'overdue_tasks', 'inactive_spoke', 'high_load', 'pending_inbox'
    severity: str  # 'info', 'warning', 'critical'
    title: str
    description: str
    action_label: str
    action_type: str  # 'reschedule', 'archive', 'navigate', 'dismiss'
    action_data: Dict[str, Any]


class SuggestionsResponse(BaseModel):
    suggestions: List[HubSuggestion]
    generated_at: str


@router.get("", response_model=SuggestionsResponse)
async def get_hub_suggestions(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Get proactive suggestions from Hub based on:
    - Overdue tasks
    - Inactive spokes
    - High load days
    """
    user_id = current_user.user_id
    suggestions: List[HubSuggestion] = []
    today = date.today()
    
    try:
        # Get LBS client
        lbs_client = await get_lbs_client(user_id, db)
        
        if lbs_client:
            # Check for overdue tasks
            overdue_suggestions = await _check_overdue_tasks(lbs_client, today)
            suggestions.extend(overdue_suggestions)
            
            # Check for high load days in the next 7 days
            high_load_suggestions = await _check_high_load_days(lbs_client, today)
            suggestions.extend(high_load_suggestions)
        
        # Check for inactive projects
        inactive_suggestions = await _check_inactive_projects(user_id, db, today)
        suggestions.extend(inactive_suggestions)
        
        
    except Exception as e:
        # Log but don't fail - suggestions are non-critical
        print(f"[Suggestions] Error generating suggestions: {e}")
    
    return SuggestionsResponse(
        suggestions=suggestions,
        generated_at=datetime.now().isoformat()
    )


async def _check_overdue_tasks(lbs_client: LBSClient, today: date) -> List[HubSuggestion]:
    """Check for tasks with past due dates that are not completed"""
    suggestions = []
    
    try:
        # Get schedule for the past week
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        
        schedule_data = await lbs_client.get_schedule(
            start_date=week_ago.isoformat(),
            end_date=yesterday.isoformat()
        )
        
        # Flat list of incomplete tasks from schedule
        overdue_tasks = []
        if isinstance(schedule_data, list):
            for day_data in schedule_data:
                for task in day_data.get("tasks", []):
                    if task.get("status") not in ["done", "skipped"]:
                        overdue_tasks.append(task)
        
        if overdue_tasks:
            count = len(overdue_tasks)
            suggestions.append(HubSuggestion(
                id=f"overdue-{uuid.uuid4().hex[:8]}",
                type="overdue_tasks",
                severity="warning" if count <= 3 else "critical",
                title=f"{count} overdue task{'s' if count > 1 else ''}",
                description=f"You have {count} task{'s' if count > 1 else ''} from the past week that {'are' if count > 1 else 'is'} not marked complete. Would you like to reschedule or skip {'them' if count > 1 else 'it'}?",
                action_label="Review Tasks",
                action_type="navigate",
                action_data={
                    "route": "/tasks",
                    "filter": "overdue",
                    "task_ids": [t.get("task_id") for t in overdue_tasks[:5]]
                }
            ))
    except Exception as e:
        print(f"[Suggestions] Error checking overdue tasks: {e}")
    
    return suggestions


async def _check_high_load_days(lbs_client: LBSClient, today: date) -> List[HubSuggestion]:
    """Check for upcoming days with high workload"""
    suggestions = []
    
    try:
        # Check next 7 days
        end_date = today + timedelta(days=7)
        
        daily_loads = await lbs_client.get_heatmap(
            start=today.isoformat(),
            end=end_date.isoformat()
        )
        
        # Find days over capacity (assuming cap of 8)
        high_load_days = [
            day for day in daily_loads 
            if day.get("adjusted_load", 0) > 8.0
        ]
        
        if high_load_days:
            count = len(high_load_days)
            worst_day = max(high_load_days, key=lambda d: d.get("adjusted_load", 0))
            worst_date = worst_day.get("date", "upcoming")
            worst_load = worst_day.get("adjusted_load", 0)
            
            suggestions.append(HubSuggestion(
                id=f"highload-{uuid.uuid4().hex[:8]}",
                type="high_load",
                severity="warning",
                title=f"High workload ahead",
                description=f"You have {count} day{'s' if count > 1 else ''} this week with load over capacity. The highest is {worst_date} with {worst_load:.1f} load. Consider redistributing tasks.",
                action_label="View Calendar",
                action_type="navigate",
                action_data={
                    "route": "/dashboard",
                    "highlight_date": worst_date
                }
            ))
    except Exception as e:
        print(f"[Suggestions] Error checking high load days: {e}")
    
    return suggestions



async def _check_inactive_projects(user_id: str, session: AsyncSession, today: date) -> List[HubSuggestion]:
    """Check for projects with no recent activity"""
    suggestions = []
    
    try:
        # Get all project nodes for the user (excluding hub)
        result = await session.execute(
            select(Project).filter(
                Project.user_id == user_id,
                Project.status != "archived"
            )
        )
        projects = result.scalars().all()
        
        inactive_threshold = today - timedelta(days=3)
        
        inactive_projects = []
        for project in projects:
            # Check last activity (updated_at)
            if project.updated_at:
                last_activity = project.updated_at.date() if hasattr(project.updated_at, 'date') else project.updated_at
                if last_activity < inactive_threshold:
                    inactive_projects.append(project.name)
        
        if inactive_projects:
            count = len(inactive_projects)
            project_names = ", ".join(inactive_projects[:3])
            if count > 3:
                project_names += f" and {count - 3} more"
            
            suggestions.append(HubSuggestion(
                id=f"inactive-{uuid.uuid4().hex[:8]}",
                type="inactive_project",
                severity="info",
                title=f"{count} inactive project{'s' if count > 1 else ''}",
                description=f"The following project{'s have' if count > 1 else ' has'} been inactive for 3+ days: {project_names}. Consider archiving or reviewing {'them' if count > 1 else 'it'}.",
                action_label="Manage Projects",
                action_type="navigate",
                action_data={
                    "route": "/projects",
                    "inactive_projects": inactive_projects
                }
            ))
    except Exception as e:
        print(f"[Suggestions] Error checking inactive projects: {e}")
    
    return suggestions




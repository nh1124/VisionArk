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

from models.database import get_session, Node
from services.lbs_client import LBSClient
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
    session: Session = Depends(get_session)
):
    """
    Get proactive suggestions from Hub based on:
    - Overdue tasks
    - Inactive spokes
    - High load days
    - Pending inbox messages
    """
    user_id = current_user.user_id
    suggestions: List[HubSuggestion] = []
    today = date.today()
    
    try:
        # Get LBS client
        lbs_client = LBSClient.from_user_settings(user_id, session)
        
        if lbs_client:
            # Check for overdue tasks
            overdue_suggestions = await _check_overdue_tasks(lbs_client, today)
            suggestions.extend(overdue_suggestions)
            
            # Check for high load days in the next 7 days
            high_load_suggestions = await _check_high_load_days(lbs_client, today)
            suggestions.extend(high_load_suggestions)
        
        # Check for inactive spokes
        inactive_suggestions = _check_inactive_spokes(user_id, session, today)
        suggestions.extend(inactive_suggestions)
        
        # Check for pending inbox messages
        inbox_suggestions = _check_pending_inbox(user_id, session)
        suggestions.extend(inbox_suggestions)
        
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
        # Get tasks from yesterday and before
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        
        tasks = lbs_client.get_tasks_in_range(
            start_date=week_ago.isoformat(),
            end_date=yesterday.isoformat()
        )
        
        # Filter for incomplete tasks
        overdue_tasks = [
            t for t in tasks 
            if t.get("status") not in ["done", "skipped"]
        ]
        
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
        
        daily_loads = lbs_client.get_load_in_period(
            start_date=today.isoformat(),
            end_date=end_date.isoformat()
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


def _check_inactive_spokes(user_id: str, session: Session, today: date) -> List[HubSuggestion]:
    """Check for spokes with no recent activity"""
    suggestions = []
    
    try:
        # Get all spoke nodes for the user
        spokes = session.query(Node).filter_by(
            user_id=user_id,
            node_type="spoke",
            status="active"
        ).all()
        
        inactive_threshold = today - timedelta(days=3)
        
        inactive_spokes = []
        for spoke in spokes:
            # Check last activity (updated_at)
            if spoke.updated_at:
                last_activity = spoke.updated_at.date() if hasattr(spoke.updated_at, 'date') else spoke.updated_at
                if last_activity < inactive_threshold:
                    inactive_spokes.append(spoke.name)
        
        if inactive_spokes:
            count = len(inactive_spokes)
            spoke_names = ", ".join(inactive_spokes[:3])
            if count > 3:
                spoke_names += f" and {count - 3} more"
            
            suggestions.append(HubSuggestion(
                id=f"inactive-{uuid.uuid4().hex[:8]}",
                type="inactive_spoke",
                severity="info",
                title=f"{count} inactive spoke{'s' if count > 1 else ''}",
                description=f"The following spoke{'s have' if count > 1 else ' has'} been inactive for 3+ days: {spoke_names}. Consider archiving or reviewing {'them' if count > 1 else 'it'}.",
                action_label="Manage Spokes",
                action_type="navigate",
                action_data={
                    "route": "/spokes",
                    "inactive_spokes": inactive_spokes
                }
            ))
    except Exception as e:
        print(f"[Suggestions] Error checking inactive spokes: {e}")
    
    return suggestions


def _check_pending_inbox(user_id: str, session: Session) -> List[HubSuggestion]:
    """Check for pending inbox messages"""
    suggestions = []
    
    try:
        from models.database import InboxMessage
        
        # Count pending messages
        pending_count = session.query(InboxMessage).filter_by(
            user_id=user_id,
            status="pending"
        ).count()
        
        if pending_count > 0:
            suggestions.append(HubSuggestion(
                id=f"inbox-{uuid.uuid4().hex[:8]}",
                type="pending_inbox",
                severity="info",
                title=f"{pending_count} pending message{'s' if pending_count > 1 else ''}",
                description=f"You have {pending_count} unprocessed message{'s' if pending_count > 1 else ''} from Spoke agents waiting in your inbox.",
                action_label="Open Inbox",
                action_type="navigate",
                action_data={
                    "route": "/hub",
                    "view": "inbox"
                }
            ))
    except Exception as e:
        print(f"[Suggestions] Error checking pending inbox: {e}")
    
    return suggestions

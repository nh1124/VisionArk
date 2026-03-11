"""
Dynamic Scheduler API

REST endpoint for schedule suggestions with smart buffering,
night mode, and fatigue adaptation.
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from datetime import date, datetime
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from domains.lbs.client import LBSClient
from api.lbs_routes import get_lbs_client
from domains.identity.auth import resolve_identity, Identity
from shared.database import get_async_db, UserSettings
from shared.encryption import decrypt_string
from domains.automation.scheduler_service import (
    calculate_schedule_v3,
    DEFAULT_SHUTDOWN_HOUR, 
    FATIGUED_SHUTDOWN_HOUR,
    FATIGUE_HIGH_THRESHOLD
)

import httpx
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scheduler", tags=["Scheduler"])


# ============================================================================
# Helper Functions
# ============================================================================

async def get_user_gemini_api_key(user_id: str, db: AsyncSession) -> Optional[str]:
    """Get user's decrypted Gemini API key from settings."""
    result = await db.execute(
        select(UserSettings).filter(UserSettings.user_id == user_id)
    )
    settings_obj = result.scalars().first()
    
    if not settings_obj or not settings_obj.ai_config:
        return None
    
    encrypted_key = settings_obj.ai_config.get("gemini_api_key")
    if not encrypted_key:
        return None
    
    try:
        return decrypt_string(encrypted_key)
    except Exception as e:
        logger.warning(f"Failed to decrypt API key: {e}")
        return None


# ============================================================================
# Request/Response Models
# ============================================================================

class ScheduleSuggestRequest(BaseModel):
    """Request body for schedule suggestion."""
    fatigue: int = Field(0, ge=0, le=5, description="Current fatigue level (0-5)")
    current_time: Optional[str] = Field(
        None, 
        description="ISO datetime to schedule from (defaults to now)"
    )
    use_agent: bool = Field(True, description="Use LLM agent for optimization")

class ScheduleSuggestResponse(BaseModel):
    """Response with generated schedule."""
    schedule: list
    overflow: list
    commands: list
    generated_at: str
    shutdown_time: str
    fatigue_level: int
    agent_used: bool = False


# ============================================================================
# Endpoints
# ============================================================================

@router.post("/suggest", response_model=ScheduleSuggestResponse)
async def suggest_schedule(
    request: ScheduleSuggestRequest,
    lbs: LBSClient = Depends(get_lbs_client),
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Generate an optimized schedule (V3 Logic).
    
    Returns an OperationRecord containing:
    - schedule: Displayable schedule
    - commands: List of CREATE_EXCEPTION ops to sync changes
    """
    try:
        # Parse current time
        if request.current_time:
            try:
                now = datetime.fromisoformat(request.current_time)
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid current_time format. Use ISO 8601."
                )
        else:
            now = datetime.now()
        
        # Fetch today's tasks and exceptions
        today = now.date()
        today_str = today.isoformat()
        
        # Parallel fetch if possible, but sequential is fine for now
        tasks = await lbs.list_tasks(active=True)
        exceptions = await lbs.get_exceptions(today_str, today_str)
        
        # Filter to only 'todo' status tasks
        todo_tasks = [t for t in tasks if t.get("status") == "todo"]
        
        print(f"⚪ SCHEDULER: Fetched {len(todo_tasks)} tasks, {len(exceptions)} exceptions")
        
        # Get condition/fatigue
        fatigue = request.fatigue
        if fatigue == 0:
            try:
                condition = await lbs.get_condition(today)
                if condition and condition.get("cognitive_fatigue"):
                    fatigue = condition.get("cognitive_fatigue", 0)
            except Exception:
                pass

        # Get API Key
        api_key = None
        if request.use_agent:
            api_key = await get_user_gemini_api_key(identity.user_id, db)
            if api_key:
                 print(f"🟢 SCHEDULER: Using Agent (User: {identity.user_id[:8]})")
            else:
                 print(f"🔴 SCHEDULER: No API Key found")

        # Call V3 Scheduler
        # (Pass None for api_key if use_agent is False to force deterministic)
        op_record = await calculate_schedule_v3(
            tasks=todo_tasks,
            exceptions=exceptions,
            fatigue=fatigue,
            now=now,
            api_key=api_key if request.use_agent else None
        )
        
        # Determine shutdown time for response
        shutdown_hour = (
            FATIGUED_SHUTDOWN_HOUR if fatigue >= FATIGUE_HIGH_THRESHOLD 
            else DEFAULT_SHUTDOWN_HOUR
        )
        shutdown_time = now.replace(
            hour=shutdown_hour, minute=0, second=0, microsecond=0
        )
        
        return ScheduleSuggestResponse(
            schedule=[item.to_dict() for item in op_record.schedule],
            overflow=op_record.overflow,
            commands=[
                {
                    "type": cmd.command_type,
                    "task_id": cmd.task_id,
                    "target_date": cmd.target_date,
                    "params": cmd.params
                }
                for cmd in op_record.commands
            ],
            generated_at=op_record.generated_at,
            shutdown_time=shutdown_time.isoformat(),
            fatigue_level=fatigue,
            agent_used=op_record.agent_used,
        )
        
    except HTTPException:
        raise
    except (httpx.ConnectError, httpx.ConnectTimeout) as e:
        logger.error(f"LBS Service unreachable: {e}")
        raise HTTPException(
            status_code=503, 
            detail="LBS service is currently unreachable. Please ensure the microservice is running."
        )
    except Exception as e:
        logger.exception(f"Schedule suggest failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def scheduler_health():
    """Health check for scheduler service."""
    return {"status": "ok", "service": "dynamic-scheduler"}

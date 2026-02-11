"""
Context Management API
Endpoints for managing conversation context rotation
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional
from domains.workspace.context_manager import ContextManager
from domains.identity.auth import resolve_identity, Identity
from shared.database import get_async_db
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/context", tags=["Context Management"])


# Pydantic models
class ArchiveRequest(BaseModel):
    force: bool = False


class ArchiveResponse(BaseModel):
    archived: bool
    timestamp: Optional[str] = None
    summary_path: Optional[str] = None
    log_path: Optional[str] = None
    message_count: Optional[int] = None
    message: str


class ContextStats(BaseModel):
    context_type: str
    context_name: str
    current_messages: int
    archived_contexts: int
    should_archive: bool
    latest_summary_available: bool



@router.post("/archive/project/{project_name}", response_model=ArchiveResponse)
async def archive_project_context(
    project_name: str,
    req: ArchiveRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """
    Archive Project conversation context (including Hub if name='hub')
    """
    try:
        # V4: Unified ContextManager. Context name corresponds to Project name.
        manager = ContextManager(identity.user_id, "project", project_name, db)
        result = await manager.archive_context(force=req.force)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Archive failed: {str(e)}")


@router.get("/stats/project/{project_name}", response_model=ContextStats)
async def get_project_context_stats(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get Project context statistics"""
    try:
        manager = ContextManager(identity.user_id, "project", project_name, db)
        if hasattr(manager, 'get_stats'):
            return await manager.get_stats()
        raise HTTPException(status_code=501, detail="Stats not implemented for project")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/summary/project/{project_name}")
async def get_project_latest_summary(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get the latest Project context summary"""
    try:
        manager = ContextManager(identity.user_id, "project", project_name, db)
        summary = await manager.get_latest_summary()
        
        if summary is None:
            raise HTTPException(status_code=404, detail="No archived summary found")
        
        return {"summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")


@router.get("/history/project/{project_name}")
async def get_project_archive_history(
    project_name: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db)
):
    """Get archive history for a Project"""
    try:
        manager = ContextManager(identity.user_id, "project", project_name, db)
        history = await manager.get_archive_history()
        return {"archives": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")


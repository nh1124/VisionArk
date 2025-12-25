"""
Context Management API
Endpoints for managing conversation context rotation
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from services.context_manager import ContextManager
from services.auth import resolve_identity, Identity, get_db

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


@router.post("/archive/hub", response_model=ArchiveResponse)
async def archive_hub_context(
    req: ArchiveRequest,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Archive Hub conversation context
    """
    try:
        manager = ContextManager(identity.user_id, "hub", "hub", db)
        result = manager.archive_context(force=req.force)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Archive failed: {str(e)}")


@router.post("/archive/spoke/{spoke_name}", response_model=ArchiveResponse)
async def archive_spoke_context(
    spoke_name: str,
    req: ArchiveRequest,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """
    Archive Spoke conversation context
    """
    try:
        manager = ContextManager(identity.user_id, "spoke", spoke_name, db)
        result = manager.archive_context(force=req.force)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Archive failed: {str(e)}")


@router.get("/stats/hub", response_model=ContextStats)
async def get_hub_context_stats(
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Get Hub context statistics"""
    try:
        manager = ContextManager(identity.user_id, "hub", "hub", db)
        # Note: get_stats might be missing in manager, let's assume it exists or wrap
        if hasattr(manager, 'get_stats'):
            return manager.get_stats()
        raise HTTPException(status_code=501, detail="Stats not implemented for hub")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/stats/spoke/{spoke_name}", response_model=ContextStats)
async def get_spoke_context_stats(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Get Spoke context statistics"""
    try:
        manager = ContextManager(identity.user_id, "spoke", spoke_name, db)
        if hasattr(manager, 'get_stats'):
            return manager.get_stats()
        raise HTTPException(status_code=501, detail="Stats not implemented for spoke")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/summary/hub")
async def get_hub_latest_summary(
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Get the latest Hub context summary"""
    try:
        manager = ContextManager(identity.user_id, "hub", "hub", db)
        summary = manager.get_latest_summary()
        
        if summary is None:
            raise HTTPException(status_code=404, detail="No archived summary found")
        
        return {"summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")


@router.get("/summary/spoke/{spoke_name}")
async def get_spoke_latest_summary(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Get the latest Spoke context summary"""
    try:
        manager = ContextManager(identity.user_id, "spoke", spoke_name, db)
        summary = manager.get_latest_summary()
        
        if summary is None:
            raise HTTPException(status_code=404, detail="No archived summary found")
        
        return {"summary": summary}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get summary: {str(e)}")


@router.get("/history/spoke/{spoke_name}")
async def get_spoke_archive_history(
    spoke_name: str,
    identity: Identity = Depends(resolve_identity),
    db: Session = Depends(get_db)
):
    """Get archive history for a Spoke"""
    try:
        manager = ContextManager(identity.user_id, "spoke", spoke_name, db)
        history = manager.get_archive_history()
        return {"archives": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")

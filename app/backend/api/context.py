"""
Context Management API
Endpoints for managing conversation context rotation
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Optional, List

from models.database import get_session, get_engine
from services.context_manager import ContextManager

router = APIRouter(prefix="/api/context", tags=["Context Management"])


# Dependency
def get_db():
    engine = get_engine()
    session = get_session(engine)
    try:
        yield session
    finally:
        session.close()


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
    db: Session = Depends(get_db)
):
    """
    Archive Hub conversation context
    
    Example:
        POST /api/context/archive/hub
        {
            "force": false
        }
    """
    try:
        manager = ContextManager("hub", "hub", db)
        result = manager.archive_context(force=req.force)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Archive failed: {str(e)}")


@router.post("/archive/spoke/{spoke_name}", response_model=ArchiveResponse)
async def archive_spoke_context(
    spoke_name: str,
    req: ArchiveRequest,
    db: Session = Depends(get_db)
):
    """
    Archive Spoke conversation context
    
    Example:
        POST /api/context/archive/spoke/research_photonics
        {
            "force": false
        }
    """
    try:
        manager = ContextManager("spoke", spoke_name, db)
        result = manager.archive_context(force=req.force)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Archive failed: {str(e)}")


@router.get("/stats/hub", response_model=ContextStats)
async def get_hub_context_stats(db: Session = Depends(get_db)):
    """Get Hub context statistics"""
    try:
        manager = ContextManager("hub", "hub", db)
        stats = manager.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/stats/spoke/{spoke_name}", response_model=ContextStats)
async def get_spoke_context_stats(
    spoke_name: str,
    db: Session = Depends(get_db)
):
    """Get Spoke context statistics"""
    try:
        manager = ContextManager("spoke", spoke_name, db)
        stats = manager.get_stats()
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get stats: {str(e)}")


@router.get("/summary/hub")
async def get_hub_latest_summary(db: Session = Depends(get_db)):
    """Get the latest Hub context summary"""
    try:
        manager = ContextManager("hub", "hub", db)
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
    db: Session = Depends(get_db)
):
    """Get the latest Spoke context summary"""
    try:
        manager = ContextManager("spoke", spoke_name, db)
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
    db: Session = Depends(get_db)
):
    """Get archive history for a Spoke"""
    try:
        manager = ContextManager("spoke", spoke_name, db)
        history = manager.get_archive_history()
        return {"archives": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get history: {str(e)}")

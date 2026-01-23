from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel

from models.database import get_async_db, ApprovalRequest, ApprovalStatus
from services.approval import ApprovalService
from models.database import get_session, get_engine
from services.auth import resolve_identity, Identity

router = APIRouter()

class ApprovalResponse(BaseModel):
    id: str
    tool_name: str
    status: str
    payload: dict
    response: Optional[dict] = None
    error_log: Optional[str] = None
    created_at: str

# Dependency for synchronous DB session (for simplicity with ApprovalService which is sync for now)
def get_db():
    engine = get_engine()
    db = get_session(engine)
    try:
        yield db
    finally:
        db.close()

@router.get("/projects/{project_id}/approvals", response_model=List[ApprovalResponse])
def list_approvals(project_id: str, db: Session = Depends(get_db), identity: Identity = Depends(resolve_identity)):
    """
    List all approval requests for a project.
    """
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.project_id == project_id
    ).order_by(ApprovalRequest.created_at.desc())
    
    requests = db.scalars(stmt).all()
    
    return [
        ApprovalResponse(
            id=req.id,
            tool_name=req.tool_name,
            status=req.status,
            payload=req.payload,
            response=req.response,
            error_log=req.error_log,
            created_at=req.created_at.isoformat()
        )
        for req in requests
    ]

@router.post("/approvals/{request_id}/approve")
def approve_request(request_id: str, db: Session = Depends(get_db), identity: Identity = Depends(resolve_identity)):
    """
    Approve and execute a request.
    """
    try:
        req = ApprovalService.approve_request(db, request_id)
        return {
            "success": True, 
            "status": req.status, 
            "result": req.response
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/approvals/{request_id}/reject")
def reject_request(request_id: str, db: Session = Depends(get_db), identity: Identity = Depends(resolve_identity)):
    """
    Reject a request.
    """
    try:
        req = ApprovalService.reject_request(db, request_id)
        return {"success": True, "status": req.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

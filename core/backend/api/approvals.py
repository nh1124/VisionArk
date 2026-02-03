from fastapi import APIRouter, Depends, HTTPException
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel

from models.database import get_async_db, ApprovalRequest, TaskType
from services.approval import ApprovalService
from queue_system.manager import QueueManager
from services.auth import resolve_identity, Identity
 
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/approvals", tags=["Approvals"])

class ApprovalResponse(BaseModel):
    id: str
    tool_name: str
    status: str
    payload: dict
    response: Optional[dict] = None
    error_log: Optional[str] = None
    created_at: str

@router.get("/project/{project_id}/list", response_model=List[ApprovalResponse])
async def list_approvals(project_id: str, db: AsyncSession = Depends(get_async_db), identity: Identity = Depends(resolve_identity)):
    """
    List all approval requests for a project.
    """
    stmt = select(ApprovalRequest).where(
        ApprovalRequest.project_id == project_id
    ).order_by(ApprovalRequest.created_at.desc())
    
    result = await db.execute(stmt)
    requests = result.scalars().all()
    
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

@router.post("/{request_id}/approve")
async def approve_request(request_id: str, db: AsyncSession = Depends(get_async_db), identity: Identity = Depends(resolve_identity)):
    """
    Approve and enqueue a request for execution.
    """
    try:
        # 1. Update status to APPROVED
        req = await ApprovalService.set_approved(db, request_id)
        
        # 2. Enqueue task for Worker
        manager = QueueManager()
        task_id = await manager.enqueue(
            user_id=req.user_id,
            message=f"Executing approved {req.tool_name} request",
            context={
                "project_id": req.project_id,
                "request_id": req.id
            },
            task_type=TaskType.APPROVAL_EXECUTION
        )
        
        return {
            "success": True, 
            "status": req.status,
            "task_id": task_id,
            "message": "Request approved and queued for execution."
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to approve request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{request_id}/reject")
async def reject_request(request_id: str, db: AsyncSession = Depends(get_async_db), identity: Identity = Depends(resolve_identity)):
    """
    Reject a request.
    """
    try:
        # 1. Update status to REJECTED
        req = await ApprovalService.reject_request(db, request_id)
        return {"success": True, "status": req.status}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to reject request: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

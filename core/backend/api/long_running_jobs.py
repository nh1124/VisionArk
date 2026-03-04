"""REST API for LongRunningJob management."""

from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import get_async_db
from domains.identity.auth import resolve_identity, Identity
from domains.long_running.services.job_service import LongRunningJobService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/long-running-jobs", tags=["Long Running Jobs"])


# ── Pydantic response schemas ─────────────────────────────────────────────────

class JobResponse(BaseModel):
    job_id: str
    status: str
    tool_name: str
    job_kind: str
    provider: Optional[str]
    model: Optional[str]
    progress: Optional[Any]
    result_path: Optional[str]
    error_code: Optional[str]
    error_message: Optional[str]
    external_ref: Optional[str]
    created_at: Optional[str]
    started_at: Optional[str]
    completed_at: Optional[str]


class EventResponse(BaseModel):
    id: str
    event_type: str
    event_payload: Optional[Any]
    created_at: Optional[str]


# ── Helper ────────────────────────────────────────────────────────────────────

def _job_to_response(job) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "tool_name": job.tool_name,
        "job_kind": job.job_kind,
        "provider": job.provider,
        "model": job.model,
        "progress": job.progress,
        "result_path": job.result_path,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "external_ref": job.external_ref,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("")
async def list_jobs(
    tool_name: Optional[str] = Query(None),
    status: Optional[str]    = Query(None),
    limit: int               = Query(50, ge=1, le=200),
    cursor: Optional[str]    = Query(None),
    identity: Identity       = Depends(resolve_identity),
    db: AsyncSession         = Depends(get_async_db),
):
    jobs = await LongRunningJobService.list_jobs(
        db, identity.user_id, tool_name=tool_name, status=status, limit=limit, cursor=cursor
    )
    return {"jobs": [_job_to_response(j) for j in jobs]}


@router.get("/{job_id}")
async def get_job(
    job_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession   = Depends(get_async_db),
):
    job = await LongRunningJobService.get_job(db, job_id, identity.user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession   = Depends(get_async_db),
):
    cancelled = await LongRunningJobService.cancel_job(db, job_id, identity.user_id)
    if not cancelled:
        raise HTTPException(
            status_code=400,
            detail="Job cannot be cancelled (not found, already completed, or not owned by you)",
        )
    return {"status": "cancelled", "job_id": job_id}


@router.get("/{job_id}/events")
async def list_events(
    job_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession   = Depends(get_async_db),
):
    events = await LongRunningJobService.list_events(db, job_id, identity.user_id)
    return {
        "events": [
            {
                "id": e.id,
                "event_type": e.event_type,
                "event_payload": e.event_payload,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]
    }

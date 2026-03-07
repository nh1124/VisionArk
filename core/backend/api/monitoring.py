"""Monitoring jobs API."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from domains.identity.auth import Identity, resolve_identity
from domains.monitoring.service import MonitoringService
from shared.database import MonitorAlert, MonitorJob, MonitorJobRun, get_async_db

router = APIRouter(prefix="/api/monitor", tags=["Monitoring"])


class MonitorJobCreateRequest(BaseModel):
    name: str
    source_type: str = "URL"
    source_config: Dict[str, Any] = Field(default_factory=dict)
    schedule_cron: str
    timezone: str = "UTC"
    detector_type: str = "RULE_BASED"
    detector_config: Dict[str, Any] = Field(default_factory=dict)
    notification_config: Dict[str, Any] = Field(default_factory=lambda: {"channel": "in_app"})
    cooldown_seconds: int = Field(default=0, ge=0)
    max_retries: int = Field(default=2, ge=0)
    retry_backoff_seconds: int = Field(default=60, ge=5)
    is_active: bool = True
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class MonitorJobUpdateRequest(BaseModel):
    name: Optional[str] = None
    source_type: Optional[str] = None
    source_config: Optional[Dict[str, Any]] = None
    schedule_cron: Optional[str] = None
    timezone: Optional[str] = None
    detector_type: Optional[str] = None
    detector_config: Optional[Dict[str, Any]] = None
    notification_config: Optional[Dict[str, Any]] = None
    cooldown_seconds: Optional[int] = Field(default=None, ge=0)
    max_retries: Optional[int] = Field(default=None, ge=0)
    retry_backoff_seconds: Optional[int] = Field(default=None, ge=5)
    is_active: Optional[bool] = None
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None


class MonitorJobSchema(BaseModel):
    id: str
    name: str
    source_type: str
    source_config: Dict[str, Any]
    schedule_cron: str
    timezone: str
    detector_type: str
    detector_config: Dict[str, Any]
    notification_config: Dict[str, Any]
    cooldown_seconds: int
    max_retries: int
    retry_backoff_seconds: int
    is_active: bool
    valid_from: Optional[datetime]
    valid_until: Optional[datetime]
    next_run_at: Optional[datetime]
    last_run_at: Optional[datetime]
    last_status: Optional[str]
    last_error: Optional[str]
    consecutive_failures: int
    created_at: datetime
    updated_at: datetime


class MonitorRunSchema(BaseModel):
    id: str
    monitor_job_id: str
    status: str
    severity: Optional[str]
    retry_count: int
    started_at: datetime
    finished_at: Optional[datetime]
    latency_ms: Optional[int]
    error_log: Optional[str]
    result_payload: Dict[str, Any]


class MonitorAlertSchema(BaseModel):
    id: str
    monitor_job_id: str
    monitor_job_run_id: Optional[str]
    severity: str
    reason: str
    dedupe_key: Optional[str]
    triggered_at: datetime
    sent_at: Optional[datetime]
    notification_status: str
    metadata_payload: Dict[str, Any]


def _job_to_schema(job: MonitorJob) -> MonitorJobSchema:
    return MonitorJobSchema(
        id=job.id,
        name=job.name,
        source_type=job.source_type,
        source_config=job.source_config or {},
        schedule_cron=job.schedule_cron,
        timezone=job.timezone,
        detector_type=job.detector_type,
        detector_config=job.detector_config or {},
        notification_config=job.notification_config or {},
        cooldown_seconds=job.cooldown_seconds,
        max_retries=job.max_retries,
        retry_backoff_seconds=job.retry_backoff_seconds,
        is_active=job.is_active,
        valid_from=job.valid_from,
        valid_until=job.valid_until,
        next_run_at=job.next_run_at,
        last_run_at=job.last_run_at,
        last_status=job.last_status,
        last_error=job.last_error,
        consecutive_failures=job.consecutive_failures,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )


def _run_to_schema(run: MonitorJobRun) -> MonitorRunSchema:
    return MonitorRunSchema(
        id=run.id,
        monitor_job_id=run.monitor_job_id,
        status=run.status,
        severity=run.severity,
        retry_count=run.retry_count,
        started_at=run.started_at,
        finished_at=run.finished_at,
        latency_ms=run.latency_ms,
        error_log=run.error_log,
        result_payload=run.result_payload or {},
    )


def _alert_to_schema(alert: MonitorAlert) -> MonitorAlertSchema:
    return MonitorAlertSchema(
        id=alert.id,
        monitor_job_id=alert.monitor_job_id,
        monitor_job_run_id=alert.monitor_job_run_id,
        severity=alert.severity,
        reason=alert.reason,
        dedupe_key=alert.dedupe_key,
        triggered_at=alert.triggered_at,
        sent_at=alert.sent_at,
        notification_status=alert.notification_status,
        metadata_payload=alert.metadata_payload or {},
    )


@router.post("/jobs", response_model=MonitorJobSchema)
async def create_monitor_job(
    request: MonitorJobCreateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    try:
        job = await service.create_job(identity.user_id, request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _job_to_schema(job)


@router.get("/jobs", response_model=List[MonitorJobSchema])
async def list_monitor_jobs(
    is_active: Optional[bool] = None,
    source_type: Optional[str] = None,
    limit: int = 100,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    jobs = await service.list_jobs(
        identity.user_id,
        is_active=is_active,
        source_type=source_type,
        limit=min(max(limit, 1), 200),
    )
    return [_job_to_schema(job) for job in jobs]


@router.get("/jobs/{job_id}", response_model=MonitorJobSchema)
async def get_monitor_job(
    job_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    job = await service.get_job(identity.user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Monitor job not found")
    return _job_to_schema(job)


@router.put("/jobs/{job_id}", response_model=MonitorJobSchema)
async def update_monitor_job(
    job_id: str,
    request: MonitorJobUpdateRequest,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    job = await service.get_job(identity.user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Monitor job not found")

    payload = request.model_dump(exclude_unset=True)
    if not payload:
        return _job_to_schema(job)

    try:
        updated = await service.update_job(job, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _job_to_schema(updated)


@router.post("/jobs/{job_id}/pause", response_model=MonitorJobSchema)
async def pause_monitor_job(
    job_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    job = await service.get_job(identity.user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Monitor job not found")
    job = await service.pause_job(job)
    return _job_to_schema(job)


@router.post("/jobs/{job_id}/resume", response_model=MonitorJobSchema)
async def resume_monitor_job(
    job_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    job = await service.get_job(identity.user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Monitor job not found")
    job = await service.resume_job(job)
    return _job_to_schema(job)


@router.post("/jobs/{job_id}/test", response_model=MonitorRunSchema)
async def test_monitor_job_once(
    job_id: str,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    job = await service.get_job(identity.user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Monitor job not found")

    run = await service.test_job_once(identity.user_id, job_id)
    return _run_to_schema(run)


@router.get("/jobs/{job_id}/runs", response_model=List[MonitorRunSchema])
async def list_monitor_job_runs(
    job_id: str,
    limit: int = 50,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    job = await service.get_job(identity.user_id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Monitor job not found")

    runs = await service.list_job_runs(identity.user_id, job_id, limit=min(max(limit, 1), 200))
    return [_run_to_schema(run) for run in runs]


@router.get("/alerts", response_model=List[MonitorAlertSchema])
async def list_monitor_alerts(
    monitor_job_id: Optional[str] = None,
    severity: Optional[str] = None,
    limit: int = 100,
    identity: Identity = Depends(resolve_identity),
    db: AsyncSession = Depends(get_async_db),
):
    service = MonitoringService(db)
    alerts = await service.list_alerts(
        identity.user_id,
        monitor_job_id=monitor_job_id,
        severity=severity,
        limit=min(max(limit, 1), 300),
    )
    return [_alert_to_schema(alert) for alert in alerts]

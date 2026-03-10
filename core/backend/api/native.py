from fastapi import APIRouter, Depends, HTTPException, Query
import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from shared.database import (
    get_async_db, NativeRun, NativeExecution, RunApproval,
    IntegrationConnection, AutomationRule, NativeDevice,
)
from domains.native.run_service import NativeRunService
from domains.identity.auth import resolve_identity, Identity

logger = logging.getLogger(__name__)

runs_router = APIRouter(prefix="/api/native-runs", tags=["Runs"])
native_router = APIRouter(prefix="/api/native", tags=["Native"])


# Pydantic schemas

class DeviceRegister(BaseModel):
    display_name: str
    device_kind: str = "desktop"
    platform: str = "other"
    client_version: Optional[str] = None
    capabilities: List[str] = []


class DevicePatch(BaseModel):
    display_name: Optional[str] = None
    is_enabled: Optional[bool] = None


class DeviceResponse(BaseModel):
    id: str
    display_name: str
    device_kind: str
    platform: str
    client_version: Optional[str]
    capabilities: List[str]
    is_enabled: bool
    status: str
    last_seen_at: Optional[str]
    created_at: str


class IntegrationCreate(BaseModel):
    provider: str
    account_ref: Optional[str] = None
    scopes: List[str] = []
    secret_ref: Optional[str] = None


class IntegrationResponse(BaseModel):
    id: str
    provider: str
    account_ref: Optional[str]
    scopes: List[str]
    health_status: str
    created_at: str


class RuleCreate(BaseModel):
    name: str
    trigger: dict
    condition: Optional[dict] = None
    action: dict
    approval_policy: str = "manual"
    limit: Optional[dict] = None


class RuleResponse(BaseModel):
    id: str
    name: str
    trigger: dict
    condition: Optional[dict]
    action: dict
    approval_policy: str
    limit: Optional[dict]
    is_active: bool
    created_at: str


# Run schemas

class RunCreate(BaseModel):
    project_id: Optional[str] = None
    agent_id: Optional[str] = None
    session_id: Optional[str] = None
    summary: Optional[str] = None
    trace_id: Optional[str] = None
    origin_type: Optional[str] = None
    origin_id: Optional[str] = None


class RunStatusUpdate(BaseModel):
    status: str
    summary: Optional[str] = None


class ExecutionCreate(BaseModel):
    kind: str
    payload: dict = {}
    risk_level: str = "low"
    target_device_id: Optional[str] = None


class ExecutionUpdate(BaseModel):
    status: str
    result: Optional[dict] = None
    error_log: Optional[str] = None


class ApprovalResponse(BaseModel):
    id: str
    execution_id: str
    status: str
    reason: Optional[str]
    requested_at: str
    decided_at: Optional[str]
    decided_by: Optional[str]


class ExecutionResponse(BaseModel):
    id: str
    run_id: str
    kind: str
    status: str
    risk_level: str
    payload: dict
    result: Optional[dict]
    error_log: Optional[str]
    target_device_id: Optional[str]
    claimed_by_device_id: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: str
    updated_at: Optional[str]
    approvals: List[ApprovalResponse]


class RunResponse(BaseModel):
    id: str
    orchestration_run_id: Optional[str]
    user_id: str
    project_id: Optional[str]
    agent_id: Optional[str]
    session_id: Optional[str]
    trace_id: Optional[str]
    origin_type: Optional[str]
    origin_id: Optional[str]
    status: str
    summary: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: str
    updated_at: Optional[str]
    executions: List[ExecutionResponse]


# Helper serializers

def _approval_to_response(a: RunApproval) -> ApprovalResponse:
    return ApprovalResponse(
        id=a.id,
        execution_id=a.execution_id,
        status=a.status,
        reason=a.reason,
        requested_at=a.requested_at.isoformat(),
        decided_at=a.decided_at.isoformat() if a.decided_at else None,
        decided_by=a.decided_by,
    )


def _exec_to_response(e: NativeRun, approvals: Optional[List[RunApproval]] = None) -> ExecutionResponse:
    resolved_approvals = approvals or []
    return ExecutionResponse(
        id=e.id,
        run_id=e.id,
        kind=e.kind,
        status=e.status,
        risk_level=e.risk_level,
        payload=e.payload or {},
        result=e.result,
        error_log=e.error_log,
        target_device_id=e.target_device_id,
        claimed_by_device_id=e.claimed_by_device_id,
        started_at=e.started_at.isoformat() if e.started_at else None,
        finished_at=e.finished_at.isoformat() if e.finished_at else None,
        created_at=e.created_at.isoformat(),
        updated_at=e.updated_at.isoformat() if e.updated_at else None,
        approvals=[_approval_to_response(a) for a in resolved_approvals],
    )


def _log_to_response(log: NativeExecution, run: NativeRun, approvals: Optional[List[RunApproval]] = None) -> ExecutionResponse:
    payload = dict(log.payload or {})
    return ExecutionResponse(
        id=log.id,
        run_id=run.id,
        kind=(payload.get("kind") if isinstance(payload, dict) else None) or run.kind,
        status=log.status,
        risk_level=run.risk_level,
        payload=payload,
        result=log.result,
        error_log=log.error_log,
        target_device_id=run.target_device_id,
        claimed_by_device_id=run.claimed_by_device_id,
        started_at=run.started_at.isoformat() if run.started_at else None,
        finished_at=run.finished_at.isoformat() if run.finished_at else None,
        created_at=log.created_at.isoformat(),
        updated_at=None,
        approvals=[_approval_to_response(a) for a in (approvals or [])],
    )


def _run_to_response(r: NativeRun, executions: Optional[List[NativeExecution]] = None, approvals: Optional[List[RunApproval]] = None) -> RunResponse:
    run_logs = executions or []
    run_result = dict(r.result or {})
    summary = run_result.get("summary")
    agent_id = run_result.get("agent_id")
    execution_responses: List[ExecutionResponse] = []
    for idx, log in enumerate(run_logs):
        log_approvals = approvals if idx == len(run_logs) - 1 else []
        execution_responses.append(_log_to_response(log, r, approvals=log_approvals))

    return RunResponse(
        id=r.id,
        orchestration_run_id=r.orchestration_run_id,
        user_id=r.user_id or "",
        project_id=r.project_id,
        agent_id=agent_id,
        session_id=r.session_id,
        trace_id=r.trace_id,
        origin_type=r.origin_type,
        origin_id=r.origin_id,
        status=r.status,
        summary=summary,
        started_at=r.started_at.isoformat() if r.started_at else None,
        finished_at=r.finished_at.isoformat() if r.finished_at else None,
        created_at=r.created_at.isoformat() if r.created_at else datetime.utcnow().isoformat(),
        updated_at=r.updated_at.isoformat() if r.updated_at else None,
        executions=execution_responses,
    )


def _device_to_response(d: NativeDevice) -> DeviceResponse:
    return DeviceResponse(
        id=d.id,
        display_name=d.display_name,
        device_kind=d.device_kind,
        platform=d.platform,
        client_version=d.client_version,
        capabilities=d.capabilities or [],
        is_enabled=d.is_enabled,
        status=d.status,
        last_seen_at=d.last_seen_at.isoformat() if d.last_seen_at else None,
        created_at=d.created_at.isoformat(),
    )


# Run endpoints

@runs_router.post("", response_model=RunResponse)
async def create_run(
    body: RunCreate,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    run = await NativeRunService.create_run(
        db=db,
        user_id=identity.user_id,
        project_id=body.project_id,
        agent_id=body.agent_id,
        session_id=body.session_id,
        summary=body.summary,
        trace_id=body.trace_id or str(uuid.uuid4()),
        origin_type=body.origin_type or "native_api",
        origin_id=body.origin_id,
    )
    execs = await NativeRunService.list_executions(db, run.id)
    approvals = await NativeRunService.list_approvals_for_run(db, run.id)
    return _run_to_response(run, execs, approvals=approvals)


@runs_router.get("", response_model=List[RunResponse])
async def list_runs(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    runs = await NativeRunService.list_runs(
        db=db,
        user_id=identity.user_id,
        status=status,
        limit=limit,
    )
    out: List[RunResponse] = []
    for run in runs:
        execs = await NativeRunService.list_executions(db, run.id)
        approvals = await NativeRunService.list_approvals_for_run(db, run.id)
        out.append(_run_to_response(run, execs, approvals=approvals))
    return out


# NOTE: /pull, /cancel, /retry, and /executions/{exec_id}/claim must appear
# before /{run_id} to avoid FastAPI routing conflicts with the path parameter.

@runs_router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Cancel a run and all its non-terminal executions."""
    try:
        run = await NativeRunService.cancel_run(db=db, run_id=run_id, user_id=identity.user_id)
        execs = await NativeRunService.list_executions(db, run.id)
        approvals = await NativeRunService.list_approvals_for_run(db, run.id)
        return _run_to_response(run, execs, approvals=approvals)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@runs_router.post("/{run_id}/retry", response_model=ExecutionResponse)
async def retry_execution(
    run_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Clone a failed/rejected execution as a new pending one."""
    run = await NativeRunService.get_run(db, run_id, identity.user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        new_exec = await NativeRunService.retry_execution(db=db, run_id=run.id, exec_id=run.id)
        return _exec_to_response(new_exec)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@runs_router.get("/pull", response_model=List[ExecutionResponse])
async def pull_executions_for_device(
    device_id: str = Query(...),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Daemon endpoint: fetch pending executions assigned to this device."""
    try:
        res = await db.execute(
            select(NativeDevice).where(
                NativeDevice.id == device_id,
                NativeDevice.user_id == identity.user_id,
            )
        )
        device = res.scalars().first()
        if not device:
            raise HTTPException(status_code=403, detail="Device not found or not owned by user")

        stmt = (
            select(NativeRun)
            .where(NativeRun.status == "pending")
            .where(
                (NativeRun.target_device_id == device_id) |
                (NativeRun.target_device_id == None)  # noqa: E711
            )
            .order_by(NativeRun.created_at.asc())
            .limit(limit)
        )
        result = await db.execute(stmt)
        execs = result.scalars().all()

        out: List[ExecutionResponse] = []
        for e in execs:
            try:
                out.append(_exec_to_response(e))
            except Exception:
                logger.exception(
                    "runs.pull.serialize_failed user=%s device=%s exec=%s",
                    identity.user_id,
                    device_id,
                    getattr(e, "id", None),
                )
        return out
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "runs.pull.failed user=%s device=%s limit=%s",
            identity.user_id,
            device_id,
            limit,
        )
        raise


class StreamBody(BaseModel):
    stdout: str = ""


class StdinBody(BaseModel):
    text: str


async def _require_device_owns_exec(
    db: AsyncSession,
    exec_id: str,
    device_id: str,
    user_id: str,
) -> NativeRun:
    """Verify the device belongs to the user and has claimed the execution."""
    res = await db.execute(
        select(NativeDevice).where(
            NativeDevice.id == device_id,
            NativeDevice.user_id == user_id,
        )
    )
    if not res.scalars().first():
        raise HTTPException(status_code=403, detail="Device not found or not owned by user")
    res = await db.execute(
        select(NativeRun).where(
            NativeRun.id == exec_id,
            NativeRun.claimed_by_device_id == device_id,
        )
    )
    exc = res.scalars().first()
    if not exc:
        raise HTTPException(status_code=403, detail="Execution not found or not claimed by this device")
    return exc


async def _require_user_owns_exec(
    db: AsyncSession,
    exec_id: str,
    user_id: str,
) -> NativeRun:
    """Verify the execution belongs to the user."""
    res = await db.execute(
        select(NativeRun).where(
            NativeRun.id == exec_id,
            NativeRun.user_id == user_id,
        )
    )
    exc = res.scalars().first()
    if not exc:
        raise HTTPException(status_code=403, detail="Execution not found or not owned by user")
    return exc


@runs_router.patch("/executions/{exec_id}/stream")
async def stream_execution_output(
    exec_id: str,
    body: StreamBody,
    device_id: str = Query(..., description="Device ID performing the stream update"),
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Daemon endpoint: post partial stdout while the process is running."""
    await _require_device_owns_exec(db, exec_id, device_id, identity.user_id)
    await NativeRunService.patch_partial_stdout(db, exec_id, body.stdout)
    return {"ok": True}


@runs_router.get("/executions/{exec_id}/stdin")
async def get_execution_stdin(
    exec_id: str,
    device_id: str = Query(..., description="Device ID polling for stdin"),
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Daemon endpoint: dequeue all pending stdin strings (one-shot read)."""
    await _require_device_owns_exec(db, exec_id, device_id, identity.user_id)
    queue = await NativeRunService.dequeue_stdin(db, exec_id)
    return {"pending": queue}


@runs_router.post("/executions/{exec_id}/stdin")
async def enqueue_execution_stdin(
    exec_id: str,
    body: StdinBody,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Agent endpoint: enqueue text to send to the running process's stdin."""
    await _require_user_owns_exec(db, exec_id, identity.user_id)
    try:
        await NativeRunService.enqueue_stdin(db, exec_id, body.text)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"ok": True}


@runs_router.post("/executions/{exec_id}/claim", response_model=ExecutionResponse)
async def claim_execution(
    exec_id: str,
    device_id: str = Query(...),
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Daemon endpoint: atomically claim a pending execution for this device."""
    res = await db.execute(
        select(NativeDevice).where(
            NativeDevice.id == device_id,
            NativeDevice.user_id == identity.user_id,
        )
    )
    device = res.scalars().first()
    if not device:
        raise HTTPException(status_code=403, detail="Device not found or not owned by user")

    # Atomic claim: update only if still pending and claimable by this device.
    claim_result = await db.execute(
        update(NativeRun)
        .where(
            NativeRun.id == exec_id,
            NativeRun.status == "pending",
            ((NativeRun.target_device_id == device_id) | (NativeRun.target_device_id == None)),  # noqa: E711
            ((NativeRun.claimed_by_device_id == None) | (NativeRun.claimed_by_device_id == device_id)),  # noqa: E711
        )
        .values(
            claimed_by_device_id=device_id,
            updated_at=datetime.utcnow(),
        )
    )
    await db.commit()

    if not claim_result.rowcount:
        # Build a precise error message for callers.
        res = await db.execute(select(NativeRun).where(NativeRun.id == exec_id))
        exc = res.scalars().first()
        if not exc:
            raise HTTPException(status_code=404, detail="Execution not found")
        if exc.status != "pending":
            raise HTTPException(status_code=409, detail=f"Execution is not claimable (status={exc.status})")
        if exc.target_device_id and exc.target_device_id != device_id:
            raise HTTPException(status_code=403, detail="Execution is targeted at a different device")
        if exc.claimed_by_device_id and exc.claimed_by_device_id != device_id:
            raise HTTPException(status_code=409, detail="Execution already claimed by another device")
        raise HTTPException(status_code=409, detail="Execution claim conflict")

    res = await db.execute(select(NativeRun).where(NativeRun.id == exec_id))
    exc = res.scalars().first()
    if not exc:
        raise HTTPException(status_code=404, detail="Execution not found after claim")
    logger.info("execution.claimed device=%s exec=%s", device_id, exec_id)
    return _exec_to_response(exc)


@runs_router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    run = await NativeRunService.get_run(db, run_id, identity.user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    execs = await NativeRunService.list_executions(db, run.id)
    approvals = await NativeRunService.list_approvals_for_run(db, run.id)
    return _run_to_response(run, execs, approvals=approvals)


@runs_router.patch("/{run_id}", response_model=RunResponse)
async def update_run(
    run_id: str,
    body: RunStatusUpdate,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    try:
        run = await NativeRunService.update_run_status(
            db=db,
            run_id=run_id,
            user_id=identity.user_id,
            status=body.status,
            summary=body.summary,
        )
        execs = await NativeRunService.list_executions(db, run.id)
        approvals = await NativeRunService.list_approvals_for_run(db, run.id)
        return _run_to_response(run, execs, approvals=approvals)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@runs_router.post("/{run_id}/executions", response_model=ExecutionResponse)
async def add_execution(
    run_id: str,
    body: ExecutionCreate,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    run = await NativeRunService.get_run(db, run_id, identity.user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    exc = await NativeRunService.add_execution(
        db=db,
        run_id=run.id,
        kind=body.kind,
        payload=body.payload,
        risk_level=body.risk_level,
        target_device_id=body.target_device_id,
    )
    approvals = await NativeRunService.list_approvals_for_run(db, run.id)
    return _log_to_response(exc, run, approvals=approvals)


@runs_router.patch("/{run_id}/status", response_model=ExecutionResponse)
async def update_execution_status(
    run_id: str,
    body: ExecutionUpdate,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Daemon endpoint: update run status. Setting waiting_approval auto-creates a RunApproval."""
    run = await NativeRunService.get_run(db, run_id, identity.user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    try:
        exc = await NativeRunService.update_execution_status(
            db=db,
            exec_id=run_id,
            status=body.status,
            result=body.result,
            error_log=body.error_log,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # Auto-create RunApproval when daemon signals waiting_approval
    if body.status == "waiting_approval":
        reason = (body.result or {}).get("approval_reason")
        await NativeRunService.request_approval(db, run_id, reason=reason)
        if run.status not in ("waiting_approval", "completed", "failed", "canceled"):
            await NativeRunService.update_run_status(db, run.id, identity.user_id, "waiting_approval")

    # Refresh to pick up updated approvals
    exc = await NativeRunService.get_execution(db, run_id)
    return _exec_to_response(exc)


@runs_router.post("/{run_id}/approve/{approval_id}", response_model=ApprovalResponse)
async def approve_execution(
    run_id: str,
    approval_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    run = await NativeRunService.get_run(db, run_id, identity.user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        approval = await NativeRunService.decide_approval(
            db=db,
            approval_id=approval_id,
            run_id=run.id,
            user_id=identity.user_id,
            decision="approved",
        )
        return _approval_to_response(approval)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@runs_router.post("/{run_id}/reject/{approval_id}", response_model=ApprovalResponse)
async def reject_execution(
    run_id: str,
    approval_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    run = await NativeRunService.get_run(db, run_id, identity.user_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    try:
        approval = await NativeRunService.decide_approval(
            db=db,
            approval_id=approval_id,
            run_id=run.id,
            user_id=identity.user_id,
            decision="rejected",
        )
        return _approval_to_response(approval)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Device management endpoints

_STALE_THRESHOLD_SECONDS = 60


@native_router.post("/devices/register", response_model=DeviceResponse)
async def register_device(
    body: DeviceRegister,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Native client self-registration (upsert by user + display_name + platform)."""
    res = await db.execute(
        select(NativeDevice).where(
            NativeDevice.user_id == identity.user_id,
            NativeDevice.display_name == body.display_name,
            NativeDevice.platform == body.platform,
        )
    )
    device = res.scalars().first()
    now = datetime.utcnow()
    if device:
        device.device_kind = body.device_kind
        device.client_version = body.client_version
        device.capabilities = body.capabilities
        device.status = "online"
        device.last_seen_at = now
    else:
        device = NativeDevice(
            id=str(uuid.uuid4()),
            user_id=identity.user_id,
            display_name=body.display_name,
            device_kind=body.device_kind,
            platform=body.platform,
            client_version=body.client_version,
            capabilities=body.capabilities,
            is_enabled=True,
            status="online",
            last_seen_at=now,
        )
        db.add(device)
    await db.commit()
    await db.refresh(device)
    logger.info("device.register user=%s device=%s", identity.user_id, device.id)
    return _device_to_response(device)


@native_router.post("/devices/{device_id}/heartbeat", response_model=DeviceResponse)
async def device_heartbeat(
    device_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Update device status to online and refresh last_seen_at."""
    res = await db.execute(
        select(NativeDevice).where(
            NativeDevice.id == device_id,
            NativeDevice.user_id == identity.user_id,
        )
    )
    device = res.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    device.status = "online"
    device.last_seen_at = datetime.utcnow()
    await db.commit()
    await db.refresh(device)
    return _device_to_response(device)


@native_router.get("/devices", response_model=List[DeviceResponse])
async def list_devices(
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """List all devices belonging to the current user (marks stale automatically)."""
    res = await db.execute(
        select(NativeDevice).where(
            NativeDevice.user_id == identity.user_id
        ).order_by(NativeDevice.created_at.desc())
    )
    devices = res.scalars().all()
    now = datetime.utcnow()
    changed = False
    for d in devices:
        if d.status == "online" and d.last_seen_at:
            age = (now - d.last_seen_at).total_seconds()
            if age > _STALE_THRESHOLD_SECONDS:
                d.status = "stale"
                changed = True
    if changed:
        await db.commit()
    return [_device_to_response(d) for d in devices]


@native_router.patch("/devices/{device_id}", response_model=DeviceResponse)
async def patch_device(
    device_id: str,
    body: DevicePatch,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Update device display_name or is_enabled (UI toggle)."""
    res = await db.execute(
        select(NativeDevice).where(
            NativeDevice.id == device_id,
            NativeDevice.user_id == identity.user_id,
        )
    )
    device = res.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if body.display_name is not None:
        device.display_name = body.display_name
    if body.is_enabled is not None:
        device.is_enabled = body.is_enabled
    await db.commit()
    await db.refresh(device)
    return _device_to_response(device)


@native_router.delete("/devices/{device_id}", status_code=204)
async def delete_device(
    device_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Remove a device registration."""
    res = await db.execute(
        select(NativeDevice).where(
            NativeDevice.id == device_id,
            NativeDevice.user_id == identity.user_id,
        )
    )
    device = res.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
        
    # Clear the target_device_id on any associated run executions to avoid FK constraint errors
    await db.execute(
        update(NativeRun)
        .where(NativeRun.target_device_id == device_id)
        .values(target_device_id=None)
    )
        
    await db.delete(device)
    await db.commit()


# Native integrations endpoints

@native_router.get("/integrations", response_model=List[IntegrationResponse])
async def list_integrations(
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.user_id == identity.user_id
    ).order_by(IntegrationConnection.created_at.desc())
    result = await db.execute(stmt)
    connections = result.scalars().all()
    return [
        IntegrationResponse(
            id=c.id,
            provider=c.provider,
            account_ref=c.account_ref,
            scopes=c.scopes or [],
            health_status=c.health_status,
            created_at=c.created_at.isoformat(),
        )
        for c in connections
    ]


@native_router.delete("/integrations/{integration_id}", status_code=204)
async def delete_integration(
    integration_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.id == integration_id,
        IntegrationConnection.user_id == identity.user_id,
    )
    result = await db.execute(stmt)
    conn = result.scalars().first()
    if not conn:
        raise HTTPException(status_code=404, detail="Integration not found")
    await db.delete(conn)
    await db.commit()


@native_router.post("/integrations", response_model=IntegrationResponse)
async def create_integration(
    body: IntegrationCreate,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    conn = IntegrationConnection(
        id=str(uuid.uuid4()),
        user_id=identity.user_id,
        provider=body.provider,
        account_ref=body.account_ref,
        scopes=body.scopes,
        secret_ref=None,
    )
    db.add(conn)
    await db.commit()
    await db.refresh(conn)
    return IntegrationResponse(
        id=conn.id,
        provider=conn.provider,
        account_ref=conn.account_ref,
        scopes=conn.scopes or [],
        health_status=conn.health_status,
        created_at=conn.created_at.isoformat(),
    )


# Automation rules endpoints

@native_router.get("/rules", response_model=List[RuleResponse])
async def list_rules(
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    stmt = select(AutomationRule).where(
        AutomationRule.user_id == identity.user_id
    ).order_by(AutomationRule.created_at.desc())
    result = await db.execute(stmt)
    rules = result.scalars().all()
    return [
        RuleResponse(
            id=r.id,
            name=r.name,
            trigger=r.trigger,
            condition=r.condition,
            action=r.action,
            approval_policy=r.approval_policy,
            limit=r.limit,
            is_active=r.is_active,
            created_at=r.created_at.isoformat(),
        )
        for r in rules
    ]


@native_router.delete("/rules/{rule_id}", status_code=204)
async def delete_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    stmt = select(AutomationRule).where(
        AutomationRule.id == rule_id,
        AutomationRule.user_id == identity.user_id,
    )
    result = await db.execute(stmt)
    rule = result.scalars().first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    await db.delete(rule)
    await db.commit()


@native_router.post("/rules", response_model=RuleResponse)
async def create_rule(
    body: RuleCreate,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    rule = AutomationRule(
        id=str(uuid.uuid4()),
        user_id=identity.user_id,
        name=body.name,
        trigger=body.trigger,
        condition=body.condition,
        action=body.action,
        approval_policy=body.approval_policy,
        limit=body.limit,
    )
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return RuleResponse(
        id=rule.id,
        name=rule.name,
        trigger=rule.trigger,
        condition=rule.condition,
        action=rule.action,
        approval_policy=rule.approval_policy,
        limit=rule.limit,
        is_active=rule.is_active,
        created_at=rule.created_at.isoformat(),
    )








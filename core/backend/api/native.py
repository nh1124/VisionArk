from fastapi import APIRouter, Depends, HTTPException, Query
import json
import logging
import re
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime

from shared.database import (
    get_async_db, Job, JobApproval, IntegrationConnection, AutomationRule,
    UserSettings,
)
from domains.native.job_service import JobService
from domains.identity.auth import resolve_identity, Identity

logger = logging.getLogger(__name__)

jobs_router = APIRouter(prefix="/api/jobs", tags=["Jobs"])
native_router = APIRouter(prefix="/api/native", tags=["Native"])


# ─── Pydantic schemas ────────────────────────────────────────────────────────

class JobCreate(BaseModel):
    type: str
    payload: dict = {}
    source: str = "native"
    project_id: Optional[str] = None
    risk_level: str = "low"
    tags: List[str] = []


class JobStatusUpdate(BaseModel):
    status: Optional[str] = None
    error_log: Optional[str] = None
    result: Optional[dict] = None


class JobResponse(BaseModel):
    id: str
    user_id: str
    project_id: Optional[str]
    source: str
    type: str
    tags: List[str]
    status: str
    risk_level: str
    payload: dict
    result: Optional[dict]
    approved_by: Optional[str]
    error_log: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: str
    updated_at: Optional[str]


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


def _job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        id=job.id,
        user_id=job.user_id,
        project_id=job.project_id,
        source=job.source,
        type=job.type,
        tags=job.tags or [],
        status=job.status,
        risk_level=job.risk_level,
        payload=job.payload or {},
        result=job.result,
        approved_by=job.approved_by,
        error_log=job.error_log,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat() if job.updated_at else None,
    )


# ─── Jobs endpoints ──────────────────────────────────────────────────────────

@jobs_router.post("", response_model=JobResponse)
async def create_job(
    body: JobCreate,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    job = await JobService.create_job(
        db=db,
        user_id=identity.user_id,
        job_type=body.type,
        payload=body.payload,
        source=body.source,
        project_id=body.project_id,
        risk_level=body.risk_level,
        tags=body.tags,
    )
    return _job_to_response(job)


@jobs_router.get("", response_model=List[JobResponse])
async def list_jobs(
    source: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    jobs = await JobService.list_jobs(
        db=db,
        user_id=identity.user_id,
        source=source,
        status=status,
        job_type=type,
        limit=limit,
    )
    return [_job_to_response(j) for j in jobs]


@jobs_router.get("/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    job = await JobService.get_job(db, job_id, identity.user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_to_response(job)


@jobs_router.patch("/{job_id}", response_model=JobResponse)
async def update_job_status(
    job_id: str,
    body: JobStatusUpdate,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    try:
        job = await JobService.update_job_status(
            db=db,
            job_id=job_id,
            status=body.status,
            error_log=body.error_log,
            result=body.result,
            user_id=identity.user_id,
        )
        return _job_to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


_DISPATCH_SYSTEM_PROMPT = """\
You are a local task planner for VisionArk. Given a job description, \
generate a JSON execution plan using ONLY the following tools:
[run_shell, read_file, write_file, list_dir, move_file, delete_file, open_app]

Tool argument schemas:
- run_shell:   {"cmd": "string", "cwd": "string (optional)", "timeout": number (optional, seconds)}
- read_file:   {"path": "string"}
- write_file:  {"path": "string", "content": "string"}
- list_dir:    {"path": "string"}
- move_file:   {"src": "string", "dst": "string"}
- delete_file: {"path": "string"}
- open_app:    {"name": "string"}

Output FORMAT (strict JSON only, no markdown fences):
{"steps": [{"id":"step_1","tool":"<name>","args":{...},"description":"<ja>","risk_level":"low|medium|high|critical"}]}

Risk level rules:
- delete_file  → always risk_level="high"
- run_shell    → "medium" minimum
- write_file   → "medium"
- move_file    → "medium"
- read_file / list_dir → "low"
- open_app     → "low"

Keep steps minimal and focused. Use Japanese for descriptions.\
"""


@jobs_router.post("/{job_id}/dispatch")
async def dispatch_job(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Generate a Plan & Execute plan for a job using the user's configured LLM.
    Returns the existing plan if the job was already dispatched.
    """
    job = await JobService.get_job(db, job_id, identity.user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    # Return existing plan if already dispatched
    if job.result and job.result.get("plan"):
        return job.result["plan"]

    # ── Resolve LLM provider ──────────────────────────────────────────
    res = await db.execute(
        select(UserSettings).where(UserSettings.user_id == identity.user_id)
    )
    settings = res.scalars().first()

    from infrastructure.llm.model_router import (
        parse_model_spec,
        get_api_key_for_provider,
        get_configured_providers,
    )
    from infrastructure.llm.provider_registry import resolve_provider
    from domains.orchestration2.engine.models.message import Message as V2Message
    from domains.orchestration2.engine.models.common import MessageRole

    provider_id, model_id, api_key = "gemini", None, None
    if settings:
        default_model = (settings.ai_config or {}).get("default_model")
        provider_id, model_id = parse_model_spec(default_model)
        api_key = get_api_key_for_provider(settings, provider_id)
        if not api_key:
            configured = get_configured_providers(settings)
            if configured:
                provider_id = configured[0]
                api_key = get_api_key_for_provider(settings, provider_id)

    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="No LLM provider configured. Add an API key in Settings.",
        )

    # ── Call LLM ──────────────────────────────────────────────────────
    user_content = (
        f"ジョブタイプ: {job.type}\n"
        f"ペイロード: {json.dumps(job.payload, ensure_ascii=False)}\n"
        f"タグ: {', '.join(job.tags or [])}"
    )
    provider = resolve_provider(provider_id, api_key, model_id)
    messages = [V2Message(role=MessageRole.USER, content=user_content)]
    try:
        llm_response = await provider.complete(messages, system=_DISPATCH_SYSTEM_PROMPT)
        raw = llm_response.content.strip()
        # Strip markdown fences if LLM adds them
        if raw.startswith("```"):
            raw = re.sub(r"^```[a-z]*\n?", "", raw)
            raw = re.sub(r"\n?```$", "", raw.strip())
        plan = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                plan = json.loads(match.group())
            except json.JSONDecodeError:
                raise HTTPException(
                    status_code=500,
                    detail=f"LLM returned invalid JSON: {raw[:300]}",
                )
        else:
            raise HTTPException(
                status_code=500,
                detail=f"LLM returned no JSON: {raw[:300]}",
            )
    except Exception as e:
        logger.error(f"LLM dispatch error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM error: {e}")

    # ── Persist plan + mark job as running ───────────────────────────
    result = {
        "plan": plan,
        "step_results": [],
        "dispatched_at": datetime.utcnow().isoformat(),
        "current_step": None,
    }
    await JobService.update_job_status(db, job_id, "running", result=result)
    return plan


@jobs_router.post("/{job_id}/retry", response_model=JobResponse)
async def retry_job(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    """Re-queue a failed or rejected job for re-execution."""
    job = await JobService.get_job(db, job_id, identity.user_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status not in ("failed", "rejected"):
        raise HTTPException(status_code=400, detail=f"Only failed/rejected jobs can be retried (status: {job.status})")
    job.status = "queued"
    job.error_log = None
    job.result = None
    job.started_at = None
    job.finished_at = None
    await db.commit()
    await db.refresh(job)
    return _job_to_response(job)


@jobs_router.post("/{job_id}/approve", response_model=JobResponse)
async def approve_job(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    try:
        job = await JobService.approve_job(db, job_id, identity.user_id)
        return _job_to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to approve job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@jobs_router.post("/{job_id}/reject", response_model=JobResponse)
async def reject_job(
    job_id: str,
    db: AsyncSession = Depends(get_async_db),
    identity: Identity = Depends(resolve_identity),
):
    try:
        job = await JobService.reject_job(db, job_id, identity.user_id)
        return _job_to_response(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to reject job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ─── Native integrations endpoints ──────────────────────────────────────────

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


# ─── Automation rules endpoints ──────────────────────────────────────────────

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

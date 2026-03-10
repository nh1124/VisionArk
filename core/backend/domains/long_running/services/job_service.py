"""LongRunningJobService — CRUD + lifecycle for LongRunningJob records."""

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import LongRunningJob, LongRunningJobEvent
from domains.long_running.models import JobCreateOptions, JobStatus, JobEventType

logger = logging.getLogger(__name__)


class LongRunningJobService:
    # ── Create / Read ─────────────────────────────────────────────────────────

    @staticmethod
    async def create_job(
        db: AsyncSession,
        user_id: str,
        tool_name: str,
        job_kind: str,
        input_payload: dict[str, Any],
        provider: Optional[str] = None,
        model: Optional[str] = None,
        options: Optional[JobCreateOptions] = None,
        trace_id: Optional[str] = None,
        origin_type: Optional[str] = None,
        origin_id: Optional[str] = None,
    ) -> LongRunningJob:
        opts = options or JobCreateOptions()
        job = LongRunningJob(
            id=str(uuid.uuid4()),
            user_id=user_id,
            project_id=opts.project_id,
            session_id=opts.session_id,
            tool_name=tool_name,
            job_kind=job_kind,
            provider=provider,
            model=model,
            input_payload=input_payload,
            trace_id=trace_id or opts.trace_id,
            origin_type=origin_type or opts.origin_type,
            origin_id=origin_id or opts.origin_id,
            status=JobStatus.QUEUED,
            sync_timeout_sec=opts.sync_timeout_sec,
            max_retries=opts.max_retries,
            external_ref=opts.external_ref,
            result_path=opts.result_path,
        )
        db.add(job)
        await db.flush()
        await LongRunningJobService.append_event(db, job.id, JobEventType.CREATED)
        await db.commit()
        await db.refresh(job)
        logger.info("long_running_job.created user=%s job=%s kind=%s", user_id, job.id, job_kind)
        return job

    @staticmethod
    async def get_job(
        db: AsyncSession,
        job_id: str,
        user_id: str,
    ) -> Optional[LongRunningJob]:
        res = await db.execute(
            select(LongRunningJob).where(
                LongRunningJob.id == job_id,
                LongRunningJob.user_id == user_id,
            )
        )
        return res.scalars().first()

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        user_id: str,
        tool_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        cursor: Optional[str] = None,
    ) -> list[LongRunningJob]:
        q = select(LongRunningJob).where(LongRunningJob.user_id == user_id)
        if tool_name:
            q = q.where(LongRunningJob.tool_name == tool_name)
        if status:
            q = q.where(LongRunningJob.status == status)
        if cursor:
            # cursor = created_at ISO string of the last item
            try:
                ts = datetime.fromisoformat(cursor)
                q = q.where(LongRunningJob.created_at < ts)
            except ValueError:
                pass
        q = q.order_by(LongRunningJob.created_at.desc()).limit(limit)
        res = await db.execute(q)
        return list(res.scalars().all())

    # ── Lifecycle transitions ─────────────────────────────────────────────────

    @staticmethod
    async def claim_job(db: AsyncSession, job_id: str, worker_id: str) -> bool:
        """Atomically move job from queued → running. Returns True if claimed."""
        result = await db.execute(
            update(LongRunningJob)
            .where(LongRunningJob.id == job_id, LongRunningJob.status == JobStatus.QUEUED)
            .values(
                status=JobStatus.RUNNING,
                started_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                external_ref=LongRunningJob.external_ref,  # preserve
            )
            .returning(LongRunningJob.id)
        )
        claimed = result.scalar() is not None
        if claimed:
            await LongRunningJobService.append_event(db, job_id, JobEventType.RUNNING, {"worker_id": worker_id})
            await db.commit()
        return claimed

    @staticmethod
    async def complete_job(
        db: AsyncSession,
        job_id: str,
        result_payload: Optional[dict] = None,
        result_path: Optional[str] = None,
    ) -> None:
        now = datetime.utcnow()
        await db.execute(
            update(LongRunningJob)
            .where(LongRunningJob.id == job_id)
            .values(
                status=JobStatus.COMPLETED,
                result_payload=result_payload,
                result_path=result_path,
                completed_at=now,
                updated_at=now,
            )
        )
        await LongRunningJobService.append_event(db, job_id, JobEventType.COMPLETED)
        await db.commit()
        logger.info("long_running_job.completed job=%s", job_id)

    @staticmethod
    async def fail_job(
        db: AsyncSession,
        job_id: str,
        error_code: str,
        error_message: str,
    ) -> None:
        now = datetime.utcnow()
        await db.execute(
            update(LongRunningJob)
            .where(LongRunningJob.id == job_id)
            .values(
                status=JobStatus.FAILED,
                error_code=error_code,
                error_message=error_message,
                completed_at=now,
                updated_at=now,
            )
        )
        await LongRunningJobService.append_event(
            db, job_id, JobEventType.FAILED, {"error_code": error_code, "message": error_message}
        )
        await db.commit()
        logger.warning("long_running_job.failed job=%s code=%s", job_id, error_code)

    @staticmethod
    async def cancel_job(db: AsyncSession, job_id: str, user_id: str) -> bool:
        """Cancel a job owned by user_id. Returns True if successfully cancelled."""
        res = await db.execute(
            select(LongRunningJob).where(
                LongRunningJob.id == job_id,
                LongRunningJob.user_id == user_id,
            )
        )
        job = res.scalars().first()
        if not job or job.status in (JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED):
            return False
        now = datetime.utcnow()
        await db.execute(
            update(LongRunningJob)
            .where(LongRunningJob.id == job_id)
            .values(status=JobStatus.CANCELLED, completed_at=now, updated_at=now)
        )
        await LongRunningJobService.append_event(db, job_id, JobEventType.CANCELLED)
        await db.commit()
        return True

    @staticmethod
    async def update_progress(
        db: AsyncSession,
        job_id: str,
        progress: dict[str, Any],
    ) -> None:
        await db.execute(
            update(LongRunningJob)
            .where(LongRunningJob.id == job_id)
            .values(progress=progress, updated_at=datetime.utcnow())
        )
        await LongRunningJobService.append_event(db, job_id, JobEventType.PROGRESS, progress)
        await db.commit()

    @staticmethod
    async def set_external_ref(db: AsyncSession, job_id: str, external_ref: str) -> None:
        await db.execute(
            update(LongRunningJob)
            .where(LongRunningJob.id == job_id)
            .values(external_ref=external_ref, updated_at=datetime.utcnow())
        )
        await db.commit()

    # ── Events ────────────────────────────────────────────────────────────────

    @staticmethod
    async def append_event(
        db: AsyncSession,
        job_id: str,
        event_type: JobEventType,
        payload: Optional[dict] = None,
    ) -> None:
        event = LongRunningJobEvent(
            id=str(uuid.uuid4()),
            job_id=job_id,
            event_type=event_type.value if isinstance(event_type, JobEventType) else event_type,
            event_payload=payload,
        )
        db.add(event)
        # Note: caller is responsible for commit

    @staticmethod
    async def list_events(
        db: AsyncSession,
        job_id: str,
        user_id: str,
    ) -> list[LongRunningJobEvent]:
        # Verify ownership first
        res = await db.execute(
            select(LongRunningJob).where(
                LongRunningJob.id == job_id,
                LongRunningJob.user_id == user_id,
            )
        )
        if not res.scalars().first():
            return []
        res2 = await db.execute(
            select(LongRunningJobEvent)
            .where(LongRunningJobEvent.job_id == job_id)
            .order_by(LongRunningJobEvent.created_at.asc())
        )
        return list(res2.scalars().all())

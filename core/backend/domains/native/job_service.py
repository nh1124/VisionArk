from datetime import datetime
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional, List

from shared.database import Job, JobApproval, JobStatus

logger = logging.getLogger(__name__)


class JobService:
    @staticmethod
    async def create_job(
        db: AsyncSession,
        user_id: str,
        job_type: str,
        payload: dict,
        source: str = "native",
        project_id: Optional[str] = None,
        risk_level: str = "low",
        tags: Optional[List[str]] = None,
    ) -> Job:
        job = Job(
            id=str(uuid.uuid4()),
            user_id=user_id,
            project_id=project_id,
            source=source,
            type=job_type,
            tags=tags or [],
            status=JobStatus.QUEUED,
            risk_level=risk_level,
            payload=payload,
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def get_job(db: AsyncSession, job_id: str, user_id: str) -> Optional[Job]:
        stmt = select(Job).where(Job.id == job_id, Job.user_id == user_id)
        result = await db.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def list_jobs(
        db: AsyncSession,
        user_id: str,
        source: Optional[str] = None,
        status: Optional[str] = None,
        job_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[Job]:
        stmt = select(Job).where(Job.user_id == user_id)
        if source:
            stmt = stmt.where(Job.source == source)
        if status:
            stmt = stmt.where(Job.status == status)
        if job_type:
            stmt = stmt.where(Job.type == job_type)
        stmt = stmt.order_by(Job.created_at.desc()).limit(limit)
        result = await db.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def update_job_status(
        db: AsyncSession,
        job_id: str,
        status: Optional[str] = None,
        error_log: Optional[str] = None,
        result: Optional[dict] = None,
        user_id: Optional[str] = None,
    ) -> Job:
        stmt = select(Job).where(Job.id == job_id)
        if user_id:
            stmt = stmt.where(Job.user_id == user_id)
        res = await db.execute(stmt)
        job = res.scalars().first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if status is not None:
            job.status = status
            if status == JobStatus.RUNNING and not job.started_at:
                job.started_at = datetime.utcnow()
            if status in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.REJECTED):
                job.finished_at = datetime.utcnow()
        if error_log is not None:
            job.error_log = error_log
        if result is not None:
            job.result = result
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def approve_job(db: AsyncSession, job_id: str, approver_id: str) -> Job:
        stmt = select(Job).where(Job.id == job_id, Job.user_id == approver_id)
        res = await db.execute(stmt)
        job = res.scalars().first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        if job.status != JobStatus.NEEDS_APPROVAL:
            raise ValueError(f"Job is not awaiting approval (status: {job.status})")
        job.status = JobStatus.QUEUED
        job.approved_by = approver_id
        await db.commit()
        await db.refresh(job)
        return job

    @staticmethod
    async def reject_job(db: AsyncSession, job_id: str, user_id: str) -> Job:
        stmt = select(Job).where(Job.id == job_id, Job.user_id == user_id)
        res = await db.execute(stmt)
        job = res.scalars().first()
        if not job:
            raise ValueError(f"Job {job_id} not found")
        job.status = JobStatus.REJECTED
        job.finished_at = datetime.utcnow()
        await db.commit()
        await db.refresh(job)
        return job

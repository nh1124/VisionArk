"""LongRunningJobExecutor — polls the DB for queued jobs and dispatches them."""

from __future__ import annotations

import asyncio
import logging
import socket

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession

from shared.database import LongRunningJob
from domains.long_running.models import JobStatus
from domains.long_running.services.job_service import LongRunningJobService

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SEC = 10
_WORKER_ID = f"executor@{socket.gethostname()}"


class LongRunningJobExecutor:
    """Background executor that polls for queued long-running jobs and dispatches handlers.

    Handlers are self-registered via @register_lrj_handler in lrj_registry.
    No manual register_handler() call is needed.
    """

    def __init__(self) -> None:
        self._engine: AsyncEngine | None = None
        self._session_maker: async_sessionmaker | None = None

    def start(self, engine: AsyncEngine) -> None:
        """Set the engine and create a session maker (call before run_forever)."""
        self._engine = engine
        self._session_maker = async_sessionmaker(
            bind=engine, expire_on_commit=False, class_=AsyncSession
        )

    async def run_forever(self) -> None:
        """Main background loop — poll every _POLL_INTERVAL_SEC seconds."""
        logger.info("[LRJobExecutor] starting background loop worker_id=%s", _WORKER_ID)
        while True:
            try:
                await self._poll_loop()
            except Exception as exc:
                logger.exception("[LRJobExecutor] poll error: %s", exc)
            await asyncio.sleep(_POLL_INTERVAL_SEC)

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _poll_loop(self) -> None:
        if self._session_maker is None:
            logger.debug("[LRJobExecutor] no engine configured, skipping poll")
            return

        from va_sdk.registry import lrj_registry

        async with self._session_maker() as db:
            res = await db.execute(
                select(LongRunningJob)
                .where(LongRunningJob.status == JobStatus.QUEUED)
                .order_by(LongRunningJob.created_at.asc())
                .limit(5)
            )
            jobs = res.scalars().all()

        for job in jobs:
            if lrj_registry.get(job.job_kind) is None:
                logger.debug(
                    "[LRJobExecutor] no handler for kind=%s job=%s, skipping", job.job_kind, job.id
                )
                continue
            asyncio.create_task(self._execute(job))

    async def _execute(self, job: LongRunningJob) -> None:
        from va_sdk.registry import lrj_registry

        async with self._session_maker() as db:
            svc = LongRunningJobService

            # Atomic claim — skip if another worker beat us
            claimed = await svc.claim_job(db, job.id, _WORKER_ID)
            if not claimed:
                logger.debug("[LRJobExecutor] job=%s already claimed, skipping", job.id)
                return

            handler_cls = lrj_registry.get(job.job_kind)
            if handler_cls is None:
                await svc.fail_job(db, job.id, "no_handler", f"No handler for kind={job.job_kind}")
                return

            handler = handler_cls()
            logger.info("[LRJobExecutor] executing job=%s kind=%s", job.id, job.job_kind)
            try:
                await handler.run(job, svc, db)
            except Exception as exc:
                logger.exception("[LRJobExecutor] job=%s handler error: %s", job.id, exc)
                try:
                    await svc.fail_job(db, job.id, "handler_exception", str(exc))
                except Exception:
                    pass

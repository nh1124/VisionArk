"""NativeRunService - domain service for Run Center operations."""

from __future__ import annotations

from datetime import datetime
import logging
import uuid
from typing import List, Optional

from sqlalchemy import or_, select, update
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import NativeRun, RunApproval, RunExecution

logger = logging.getLogger(__name__)


class NativeRunService:
    @staticmethod
    async def _resolve_run_by_identifier(
        db: AsyncSession,
        run_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[NativeRun]:
        stmt = select(NativeRun).where(
            or_(
                NativeRun.id == run_id,
                NativeRun.orchestration_run_id == run_id,
            )
        )
        if user_id:
            stmt = stmt.where(NativeRun.user_id == user_id)
        res = await db.execute(stmt)
        return res.scalars().first()

    @staticmethod
    async def create_run(
        db: AsyncSession,
        user_id: str,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        summary: Optional[str] = None,
        trace_id: Optional[str] = None,
        origin_type: Optional[str] = None,
        origin_id: Optional[str] = None,
    ) -> NativeRun:
        run = NativeRun(
            id=str(uuid.uuid4()),
            user_id=user_id,
            project_id=project_id,
            agent_id=agent_id,
            session_id=session_id,
            status="queued",
            summary=summary,
            trace_id=trace_id,
            origin_type=origin_type,
            origin_id=origin_id,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        logger.info("native_run.created user=%s run=%s", user_id, run.id)
        return run

    @staticmethod
    async def create_run_from_orchestration(
        db: AsyncSession,
        run_id: str,
        user_id: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        summary: Optional[str] = None,
        trace_id: Optional[str] = None,
        origin_type: Optional[str] = "orchestration_run",
        origin_id: Optional[str] = None,
    ) -> NativeRun:
        native_run_id = str(uuid.uuid4())
        run = NativeRun(
            id=native_run_id,
            orchestration_run_id=run_id,
            user_id=user_id,
            project_id=project_id,
            session_id=session_id,
            status="running",
            summary=summary,
            started_at=datetime.utcnow(),
            trace_id=trace_id,
            origin_type=origin_type,
            origin_id=origin_id or run_id,
        )
        db.add(run)
        await db.flush()
        logger.info(
            "native_run.created_from_orchestration user=%s native_run=%s orchestration_run=%s",
            user_id,
            native_run_id,
            run_id,
        )
        return run

    @staticmethod
    async def finish_run(
        db: AsyncSession,
        run_id: str,
        status: str,
    ) -> None:
        await db.execute(
            sa_update(NativeRun)
            .where(
                or_(
                    NativeRun.id == run_id,
                    NativeRun.orchestration_run_id == run_id,
                )
            )
            .values(
                status=status,
                finished_at=datetime.utcnow(),
            )
        )
        await db.flush()
        logger.info("native_run.finished run=%s status=%s", run_id, status)

    @staticmethod
    async def get_native_run_by_orchestration_run_id(
        db: AsyncSession,
        orchestration_run_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[NativeRun]:
        stmt = select(NativeRun).where(NativeRun.orchestration_run_id == orchestration_run_id)
        if user_id:
            stmt = stmt.where(NativeRun.user_id == user_id)
        res = await db.execute(stmt)
        return res.scalars().first()

    @staticmethod
    async def get_run(
        db: AsyncSession,
        run_id: str,
        user_id: str,
    ) -> Optional[NativeRun]:
        return await NativeRunService._resolve_run_by_identifier(db, run_id, user_id)

    @staticmethod
    async def list_runs(
        db: AsyncSession,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[NativeRun]:
        stmt = select(NativeRun).where(NativeRun.user_id == user_id)
        if status:
            stmt = stmt.where(NativeRun.status == status)
        stmt = stmt.order_by(NativeRun.created_at.desc()).limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_run_status(
        db: AsyncSession,
        run_id: str,
        user_id: str,
        status: str,
        summary: Optional[str] = None,
    ) -> NativeRun:
        run = await NativeRunService._resolve_run_by_identifier(db, run_id, user_id)
        if not run:
            raise ValueError(f"NativeRun {run_id} not found")
        prev = run.status
        run.status = status
        if status == "running" and not run.started_at:
            run.started_at = datetime.utcnow()
        if status in ("completed", "failed", "canceled"):
            run.finished_at = datetime.utcnow()
        if summary is not None:
            run.summary = summary
        await db.commit()
        await db.refresh(run)
        logger.info("native_run.updated user=%s run=%s %s->%s", user_id, run.id, prev, status)
        return run

    @staticmethod
    async def add_execution(
        db: AsyncSession,
        run_id: str,
        kind: str,
        payload: dict,
        risk_level: str = "low",
        target_device_id: Optional[str] = None,
    ) -> RunExecution:
        exc = RunExecution(
            id=str(uuid.uuid4()),
            run_id=run_id,
            kind=kind,
            status="pending",
            risk_level=risk_level,
            payload=payload,
            target_device_id=target_device_id,
        )
        db.add(exc)
        await db.commit()
        await db.refresh(exc)
        logger.info("execution.created run=%s exec=%s kind=%s", run_id, exc.id, kind)
        return exc

    @staticmethod
    async def get_execution(
        db: AsyncSession,
        exec_id: str,
    ) -> Optional[RunExecution]:
        res = await db.execute(select(RunExecution).where(RunExecution.id == exec_id))
        return res.scalars().first()

    @staticmethod
    async def list_executions(
        db: AsyncSession,
        run_id: str,
    ) -> List[RunExecution]:
        res = await db.execute(
            select(RunExecution)
            .where(RunExecution.run_id == run_id)
            .order_by(RunExecution.created_at.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def update_execution_status(
        db: AsyncSession,
        exec_id: str,
        status: str,
        result: Optional[dict] = None,
        error_log: Optional[str] = None,
    ) -> RunExecution:
        res = await db.execute(select(RunExecution).where(RunExecution.id == exec_id))
        exc = res.scalars().first()
        if not exc:
            raise ValueError(f"RunExecution {exec_id} not found")
        prev = exc.status
        exc.status = status
        if status == "running" and not exc.started_at:
            exc.started_at = datetime.utcnow()
        if status in ("succeeded", "failed", "rejected"):
            exc.finished_at = datetime.utcnow()
        if result is not None:
            exc.result = result
        if error_log is not None:
            exc.error_log = error_log
        await db.commit()
        await db.refresh(exc)
        logger.info("execution.updated exec=%s %s->%s", exec_id, prev, status)
        return exc

    @staticmethod
    async def patch_partial_stdout(
        db: AsyncSession,
        exec_id: str,
        stdout: str,
    ) -> None:
        await db.execute(
            update(RunExecution)
            .where(RunExecution.id == exec_id)
            .values(partial_stdout=stdout)
        )
        await db.commit()

    @staticmethod
    async def get_partial_stdout(db: AsyncSession, exec_id: str) -> Optional[str]:
        res = await db.execute(select(RunExecution).where(RunExecution.id == exec_id))
        exc = res.scalars().first()
        return exc.partial_stdout if exc else None

    @staticmethod
    async def enqueue_stdin(db: AsyncSession, exec_id: str, text: str) -> None:
        res = await db.execute(select(RunExecution).where(RunExecution.id == exec_id))
        exc = res.scalars().first()
        if not exc:
            raise ValueError(f"RunExecution {exec_id} not found")
        queue = list(exc.stdin_queue or [])
        queue.append(text)
        exc.stdin_queue = queue
        await db.commit()
        logger.info("execution.stdin_enqueued exec=%s text_len=%d", exec_id, len(text))

    @staticmethod
    async def dequeue_stdin(db: AsyncSession, exec_id: str) -> list:
        res = await db.execute(select(RunExecution).where(RunExecution.id == exec_id))
        exc = res.scalars().first()
        if not exc:
            return []
        queue = list(exc.stdin_queue or [])
        if queue:
            exc.stdin_queue = []
            await db.commit()
        return queue

    @staticmethod
    async def cancel_run(
        db: AsyncSession,
        run_id: str,
        user_id: str,
    ) -> NativeRun:
        run = await NativeRunService._resolve_run_by_identifier(db, run_id, user_id)
        if not run:
            raise ValueError(f"NativeRun {run_id} not found")
        if run.status in ("completed", "failed", "canceled"):
            raise ValueError(f"Run already in terminal state: {run.status}")

        non_terminal = ("pending", "running", "waiting_approval")
        await db.execute(
            update(RunExecution)
            .where(
                RunExecution.run_id == run.id,
                RunExecution.status.in_(non_terminal),
            )
            .values(status="failed", error_log="Run canceled by user", finished_at=datetime.utcnow())
        )

        run.status = "canceled"
        run.finished_at = datetime.utcnow()
        await db.commit()
        await db.refresh(run)
        logger.info("native_run.canceled user=%s run=%s", user_id, run.id)
        return run

    @staticmethod
    async def retry_execution(
        db: AsyncSession,
        run_id: str,
        exec_id: str,
    ) -> RunExecution:
        run = await NativeRunService._resolve_run_by_identifier(db, run_id, user_id=None)
        if not run:
            raise ValueError(f"NativeRun {run_id} not found")

        res = await db.execute(
            select(RunExecution).where(
                RunExecution.id == exec_id,
                RunExecution.run_id == run.id,
            )
        )
        original = res.scalars().first()
        if not original:
            raise ValueError(f"RunExecution {exec_id} not found")
        if original.status not in ("failed", "rejected"):
            raise ValueError(f"Only failed/rejected executions can be retried, got: {original.status}")

        new_exec = RunExecution(
            id=str(uuid.uuid4()),
            run_id=run.id,
            kind=original.kind,
            status="pending",
            risk_level=original.risk_level,
            payload=original.payload or {},
            target_device_id=original.target_device_id,
        )
        db.add(new_exec)

        if run.status in ("completed", "failed", "canceled"):
            run.status = "running"
            run.finished_at = None

        await db.commit()
        await db.refresh(new_exec)
        logger.info("execution.retried original=%s new=%s run=%s", exec_id, new_exec.id, run.id)
        return new_exec

    @staticmethod
    async def request_approval(
        db: AsyncSession,
        execution_id: str,
        run_id: str,
        reason: Optional[str] = None,
    ) -> RunApproval:
        approval = RunApproval(
            id=str(uuid.uuid4()),
            execution_id=execution_id,
            run_id=run_id,
            status="pending",
            reason=reason,
        )
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        logger.info("approval.requested exec=%s approval=%s", execution_id, approval.id)
        return approval

    @staticmethod
    async def get_pending_approvals(
        db: AsyncSession,
        run_id: str,
    ) -> List[RunApproval]:
        res = await db.execute(
            select(RunApproval)
            .where(
                RunApproval.run_id == run_id,
                RunApproval.status == "pending",
            )
            .order_by(RunApproval.requested_at.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def list_approvals_for_run(
        db: AsyncSession,
        run_id: str,
    ) -> List[RunApproval]:
        res = await db.execute(
            select(RunApproval)
            .where(RunApproval.run_id == run_id)
            .order_by(RunApproval.requested_at.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def decide_approval(
        db: AsyncSession,
        approval_id: str,
        run_id: str,
        user_id: str,
        decision: str,  # approved | rejected
    ) -> RunApproval:
        res = await db.execute(
            select(RunApproval).where(
                RunApproval.id == approval_id,
                RunApproval.run_id == run_id,
                RunApproval.status == "pending",
            )
        )
        approval = res.scalars().first()
        if not approval:
            raise ValueError(f"RunApproval {approval_id} not found or not pending")
        approval.status = decision
        approval.decided_at = datetime.utcnow()
        approval.decided_by = user_id
        await NativeRunService.update_execution_status(
            db,
            approval.execution_id,
            status="running" if decision == "approved" else "rejected",
        )
        await db.commit()
        await db.refresh(approval)
        logger.info(
            "approval.decided approval=%s exec=%s decision=%s by=%s",
            approval_id,
            approval.execution_id,
            decision,
            user_id,
        )
        return approval

"""NativeRunService - NativeRun unit management with NativeExecution logs."""

from __future__ import annotations

from datetime import datetime
import logging
import uuid
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import NativeExecution, NativeRun, RunApproval

logger = logging.getLogger(__name__)


class NativeRunService:
    @staticmethod
    async def _append_log(
        db: AsyncSession,
        native_run_id: str,
        status: str,
        event_type: str = "status",
        payload: Optional[dict] = None,
        result: Optional[dict] = None,
        error_log: Optional[str] = None,
    ) -> NativeExecution:
        log = NativeExecution(
            id=str(uuid.uuid4()),
            native_run_id=native_run_id,
            status=status,
            event_type=event_type,
            payload=payload or {},
            result=result,
            error_log=error_log,
        )
        db.add(log)
        await db.flush()
        return log

    @staticmethod
    async def _resolve_run_by_identifier(
        db: AsyncSession,
        run_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[NativeRun]:
        stmt = select(NativeRun).where(NativeRun.id == run_id)
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
        orchestration_run_id: Optional[str] = None,
        kind: str = "manual",
        payload: Optional[dict] = None,
        risk_level: str = "low",
        target_device_id: Optional[str] = None,
    ) -> NativeRun:
        native_run = NativeRun(
            id=str(uuid.uuid4()),
            orchestration_run_id=orchestration_run_id,
            user_id=user_id,
            project_id=project_id,
            session_id=session_id,
            trace_id=trace_id,
            origin_type=origin_type,
            origin_id=origin_id,
            kind=kind,
            status="pending",
            risk_level=risk_level,
            payload=payload or {},
            target_device_id=target_device_id,
            result={"summary": summary, "agent_id": agent_id} if summary or agent_id else None,
        )
        db.add(native_run)
        await db.flush()
        await NativeRunService._append_log(
            db,
            native_run.id,
            status="pending",
            event_type="created",
            payload={"kind": kind, "summary": summary, "agent_id": agent_id},
        )
        await db.commit()
        await db.refresh(native_run)
        logger.info("native_run.created user=%s run=%s kind=%s", user_id, native_run.id, kind)
        return native_run

    @staticmethod
    async def finish_run(
        db: AsyncSession,
        run_id: str,
        status: str,
    ) -> None:
        run = await NativeRunService._resolve_run_by_identifier(db, run_id)
        if not run:
            return
        run.status = status
        run.updated_at = datetime.utcnow()
        if status in ("succeeded", "failed", "rejected", "canceled", "cancelled"):
            run.finished_at = datetime.utcnow()
        await NativeRunService._append_log(db, run.id, status=status, event_type="finished")
        await db.commit()
        logger.info("native_run.finished run=%s status=%s", run_id, status)

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
        if status and status != "active":
            stmt = stmt.where(NativeRun.status == status)
        stmt = stmt.order_by(NativeRun.created_at.desc()).limit(limit)
        res = await db.execute(stmt)
        rows = list(res.scalars().all())
        if status == "active":
            return [r for r in rows if r.status in ("pending", "running", "waiting_approval")]
        return rows

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
            raise ValueError(f"Run {run_id} not found")
        prev = run.status
        run.status = status
        run.updated_at = datetime.utcnow()
        if status in ("succeeded", "failed", "rejected", "canceled", "cancelled"):
            run.finished_at = datetime.utcnow()
        if summary is not None:
            result = dict(run.result or {})
            result["summary"] = summary
            run.result = result
        await NativeRunService._append_log(
            db,
            run.id,
            status=status,
            event_type="status",
            payload={"previous_status": prev},
        )
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
    ) -> NativeExecution:
        run = await NativeRunService._resolve_run_by_identifier(db, run_id)
        if not run:
            raise ValueError(f"NativeRun {run_id} not found")
        if target_device_id:
            run.target_device_id = target_device_id
        if risk_level:
            run.risk_level = risk_level
        if kind:
            run.kind = kind
        if payload is not None:
            run.payload = payload
        run.updated_at = datetime.utcnow()
        log = await NativeRunService._append_log(
            db,
            run.id,
            status=run.status,
            event_type=kind or "log",
            payload=payload or {},
        )
        await db.commit()
        await db.refresh(log)
        return log

    @staticmethod
    async def get_execution(
        db: AsyncSession,
        exec_id: str,
    ) -> Optional[NativeRun]:
        # Compatibility: execution_id is treated as NativeRun.id for daemon APIs.
        return await NativeRunService._resolve_run_by_identifier(db, exec_id)

    @staticmethod
    async def list_executions(
        db: AsyncSession,
        run_id: str,
    ) -> List[NativeExecution]:
        res = await db.execute(
            select(NativeExecution)
            .where(NativeExecution.native_run_id == run_id)
            .order_by(NativeExecution.created_at.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def update_execution_status(
        db: AsyncSession,
        exec_id: str,
        status: str,
        result: Optional[dict] = None,
        error_log: Optional[str] = None,
    ) -> NativeRun:
        run = await NativeRunService._resolve_run_by_identifier(db, exec_id)
        if not run:
            raise ValueError(f"NativeRun {exec_id} not found")
        prev = run.status
        run.status = status
        run.updated_at = datetime.utcnow()
        if status == "running" and not run.started_at:
            run.started_at = datetime.utcnow()
        if status in ("succeeded", "failed", "rejected", "canceled", "cancelled"):
            run.finished_at = datetime.utcnow()
        if result is not None:
            run.result = result
        if error_log is not None:
            run.error_log = error_log
        await NativeRunService._append_log(
            db,
            run.id,
            status=status,
            event_type="status",
            result=result,
            error_log=error_log,
            payload={"previous_status": prev},
        )
        await db.commit()
        await db.refresh(run)
        logger.info("native_run.status updated run=%s %s->%s", exec_id, prev, status)
        return run

    @staticmethod
    async def patch_partial_stdout(
        db: AsyncSession,
        exec_id: str,
        stdout: str,
    ) -> None:
        run = await NativeRunService._resolve_run_by_identifier(db, exec_id)
        if not run:
            raise ValueError(f"NativeRun {exec_id} not found")
        run.partial_stdout = stdout
        await NativeRunService._append_log(
            db,
            run.id,
            status=run.status,
            event_type="stdout",
            payload={"stdout": stdout},
        )
        await db.commit()

    @staticmethod
    async def get_partial_stdout(db: AsyncSession, exec_id: str) -> Optional[str]:
        run = await NativeRunService._resolve_run_by_identifier(db, exec_id)
        return run.partial_stdout if run else None

    @staticmethod
    async def enqueue_stdin(db: AsyncSession, exec_id: str, text: str) -> None:
        run = await NativeRunService._resolve_run_by_identifier(db, exec_id)
        if not run:
            raise ValueError(f"NativeRun {exec_id} not found")
        queue = list(run.stdin_queue or [])
        queue.append(text)
        run.stdin_queue = queue
        await NativeRunService._append_log(
            db,
            run.id,
            status=run.status,
            event_type="stdin.enqueue",
            payload={"text": text},
        )
        await db.commit()

    @staticmethod
    async def dequeue_stdin(db: AsyncSession, exec_id: str) -> list:
        run = await NativeRunService._resolve_run_by_identifier(db, exec_id)
        if not run:
            return []
        queue = list(run.stdin_queue or [])
        if queue:
            run.stdin_queue = []
            await NativeRunService._append_log(
                db,
                run.id,
                status=run.status,
                event_type="stdin.dequeue",
                payload={"count": len(queue)},
            )
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
            raise ValueError(f"Run {run_id} not found")
        if run.status in ("succeeded", "failed", "rejected", "canceled", "cancelled"):
            raise ValueError(f"Run already in terminal state: {run.status}")

        run.status = "canceled"
        run.error_log = "Run canceled by user"
        run.finished_at = datetime.utcnow()
        run.updated_at = datetime.utcnow()
        await NativeRunService._append_log(
            db,
            run.id,
            status="canceled",
            event_type="cancel",
            error_log=run.error_log,
        )
        await db.commit()
        await db.refresh(run)
        logger.info("native_run.canceled user=%s run=%s", user_id, run.id)
        return run

    @staticmethod
    async def retry_execution(
        db: AsyncSession,
        run_id: str,
        exec_id: str,
    ) -> NativeRun:
        source: Optional[NativeRun] = None
        if exec_id == run_id:
            source = await NativeRunService._resolve_run_by_identifier(db, run_id)
        else:
            # Compatibility: allow retry requests that pass a log id.
            log_res = await db.execute(select(NativeExecution).where(NativeExecution.id == exec_id))
            log_row = log_res.scalars().first()
            if log_row and log_row.native_run_id == run_id:
                source = await NativeRunService._resolve_run_by_identifier(db, run_id)

        if not source:
            raise ValueError(f"NativeRun {run_id} not found")
        if source.status not in ("failed", "rejected", "canceled", "cancelled"):
            raise ValueError(f"Only failed/rejected/canceled runs can be retried, got: {source.status}")

        retry = NativeRun(
            id=str(uuid.uuid4()),
            orchestration_run_id=source.orchestration_run_id,
            user_id=source.user_id,
            project_id=source.project_id,
            session_id=source.session_id,
            trace_id=source.trace_id,
            origin_type=source.origin_type,
            origin_id=source.origin_id,
            kind=source.kind,
            status="pending",
            risk_level=source.risk_level,
            payload=source.payload or {},
            target_device_id=source.target_device_id,
        )
        db.add(retry)
        await db.flush()
        await NativeRunService._append_log(
            db,
            retry.id,
            status="pending",
            event_type="retry",
            payload={"source_run_id": source.id},
        )
        await db.commit()
        await db.refresh(retry)
        logger.info("native_run.retried source=%s retry=%s", source.id, retry.id)
        return retry

    @staticmethod
    async def request_approval(
        db: AsyncSession,
        execution_id: str,
        reason: Optional[str] = None,
    ) -> RunApproval:
        approval = RunApproval(
            id=str(uuid.uuid4()),
            execution_id=execution_id,
            status="pending",
            reason=reason,
        )
        db.add(approval)
        await NativeRunService._append_log(
            db,
            execution_id,
            status="waiting_approval",
            event_type="approval.requested",
            payload={"approval_id": approval.id, "reason": reason},
        )
        await db.commit()
        await db.refresh(approval)
        logger.info("approval.requested run=%s approval=%s", execution_id, approval.id)
        return approval

    @staticmethod
    async def get_pending_approvals(
        db: AsyncSession,
        run_id: str,
    ) -> List[RunApproval]:
        res = await db.execute(
            select(RunApproval)
            .where(
                RunApproval.execution_id == run_id,
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
            .where(RunApproval.execution_id == run_id)
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
                RunApproval.execution_id == run_id,
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
            error_log="Rejected by user" if decision == "rejected" else None,
        )
        await db.commit()
        await db.refresh(approval)
        logger.info(
            "approval.decided approval=%s run=%s decision=%s by=%s",
            approval_id,
            run_id,
            decision,
            user_id,
        )
        return approval

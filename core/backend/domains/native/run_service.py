"""RunService — Run Center のドメインサービス.

階層:
  AgentRun     … 1 エージェント実行セッション
  RunExecution … Run 内の実行イベント（旧 Job 相当）
  RunApproval  … Execution に紐づく承認要求
"""

from datetime import datetime
import uuid
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import Optional, List

from shared.database import AgentRun, RunExecution, RunApproval

logger = logging.getLogger(__name__)


class RunService:
    # ── AgentRun ──────────────────────────────────────────────────────────────

    @staticmethod
    async def create_run(
        db: AsyncSession,
        user_id: str,
        project_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> AgentRun:
        run = AgentRun(
            id=str(uuid.uuid4()),
            user_id=user_id,
            project_id=project_id,
            agent_id=agent_id,
            session_id=session_id,
            status="queued",
            summary=summary,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        logger.info("run.created user=%s run=%s", user_id, run.id)
        return run

    @staticmethod
    async def get_run(db: AsyncSession, run_id: str, user_id: str) -> Optional[AgentRun]:
        res = await db.execute(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        )
        return res.scalars().first()

    @staticmethod
    async def list_runs(
        db: AsyncSession,
        user_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[AgentRun]:
        stmt = select(AgentRun).where(AgentRun.user_id == user_id)
        if status:
            stmt = stmt.where(AgentRun.status == status)
        stmt = stmt.order_by(AgentRun.created_at.desc()).limit(limit)
        res = await db.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def update_run_status(
        db: AsyncSession,
        run_id: str,
        user_id: str,
        status: str,
        summary: Optional[str] = None,
    ) -> AgentRun:
        res = await db.execute(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        )
        run = res.scalars().first()
        if not run:
            raise ValueError(f"AgentRun {run_id} not found")
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
        logger.info("run.updated user=%s run=%s %s->%s", user_id, run_id, prev, status)
        return run

    # ── RunExecution ──────────────────────────────────────────────────────────

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
        db: AsyncSession, exec_id: str
    ) -> Optional[RunExecution]:
        res = await db.execute(
            select(RunExecution).where(RunExecution.id == exec_id)
        )
        return res.scalars().first()

    @staticmethod
    async def list_executions(
        db: AsyncSession, run_id: str
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
        res = await db.execute(
            select(RunExecution).where(RunExecution.id == exec_id)
        )
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

    # ── RunApproval ───────────────────────────────────────────────────────────

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
        db: AsyncSession, run_id: str
    ) -> List[RunApproval]:
        res = await db.execute(
            select(RunApproval).where(
                RunApproval.run_id == run_id,
                RunApproval.status == "pending",
            ).order_by(RunApproval.requested_at.asc())
        )
        return list(res.scalars().all())

    @staticmethod
    async def list_approvals_for_run(
        db: AsyncSession, run_id: str
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
        decision: str,  # "approved" | "rejected"
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
        # Propagate decision to the execution
        await RunService.update_execution_status(
            db,
            approval.execution_id,
            status="running" if decision == "approved" else "rejected",
        )
        await db.commit()
        await db.refresh(approval)
        logger.info(
            "approval.decided approval=%s exec=%s decision=%s by=%s",
            approval_id, approval.execution_id, decision, user_id,
        )
        return approval

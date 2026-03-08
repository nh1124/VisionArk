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
    async def create_run_from_orchestration(
        db: AsyncSession,
        run_id: str,
        user_id: str,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        summary: Optional[str] = None,
    ) -> AgentRun:
        """orchestration2 engine の run_id を PK として AgentRun を作成する.

        FK: agent_runs.id -> orchestration_runs.run_id
        この関数は engine.execute_run() 呼び出し後に run_id が確定してから呼ぶこと。
        """
        run = AgentRun(
            id=run_id,
            user_id=user_id,
            project_id=project_id,
            session_id=session_id,
            status="running",
            summary=summary,
            started_at=datetime.utcnow(),
        )
        db.add(run)
        await db.flush()
        logger.info("run.created_from_orchestration user=%s run=%s", user_id, run_id)
        return run

    @staticmethod
    async def finish_run(
        db: AsyncSession,
        run_id: str,
        status: str,
    ) -> None:
        """run_id で AgentRun のステータスを終端状態に更新する (user_id 不要)."""
        from sqlalchemy import update as sa_update
        await db.execute(
            sa_update(AgentRun)
            .where(AgentRun.id == run_id)
            .values(
                status=status,
                finished_at=datetime.utcnow(),
            )
        )
        await db.flush()
        logger.info("run.finished run=%s status=%s", run_id, status)

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

    # ── Streaming / stdin ─────────────────────────────────────────────────────

    @staticmethod
    async def patch_partial_stdout(
        db: AsyncSession,
        exec_id: str,
        stdout: str,
    ) -> None:
        """Daemon calls this to post partial stdout while the process is running."""
        await db.execute(
            update(RunExecution)
            .where(RunExecution.id == exec_id)
            .values(partial_stdout=stdout)
        )
        await db.commit()

    @staticmethod
    async def get_partial_stdout(db: AsyncSession, exec_id: str) -> Optional[str]:
        res = await db.execute(
            select(RunExecution).where(RunExecution.id == exec_id)
        )
        exc = res.scalars().first()
        return exc.partial_stdout if exc else None

    @staticmethod
    async def enqueue_stdin(db: AsyncSession, exec_id: str, text: str) -> None:
        """Agent calls this to send input to the running process."""
        res = await db.execute(
            select(RunExecution).where(RunExecution.id == exec_id)
        )
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
        """Daemon calls this to atomically dequeue all pending stdin strings."""
        res = await db.execute(
            select(RunExecution).where(RunExecution.id == exec_id)
        )
        exc = res.scalars().first()
        if not exc:
            return []
        queue = list(exc.stdin_queue or [])
        if queue:
            exc.stdin_queue = []
            await db.commit()
        return queue

    # ── Cancel / Retry ────────────────────────────────────────────────────────

    @staticmethod
    async def cancel_run(
        db: AsyncSession,
        run_id: str,
        user_id: str,
    ) -> AgentRun:
        """Cancel a run and all its non-terminal executions."""
        res = await db.execute(
            select(AgentRun).where(AgentRun.id == run_id, AgentRun.user_id == user_id)
        )
        run = res.scalars().first()
        if not run:
            raise ValueError(f"AgentRun {run_id} not found")
        if run.status in ("completed", "failed", "canceled"):
            raise ValueError(f"Run already in terminal state: {run.status}")

        # Bulk-cancel non-terminal executions
        non_terminal = ("pending", "running", "waiting_approval")
        await db.execute(
            update(RunExecution)
            .where(
                RunExecution.run_id == run_id,
                RunExecution.status.in_(non_terminal),
            )
            .values(status="failed", error_log="Run canceled by user", finished_at=datetime.utcnow())
        )

        run.status = "canceled"
        run.finished_at = datetime.utcnow()
        await db.commit()
        await db.refresh(run)
        logger.info("run.canceled user=%s run=%s", user_id, run_id)
        return run

    @staticmethod
    async def retry_execution(
        db: AsyncSession,
        run_id: str,
        exec_id: str,
    ) -> RunExecution:
        """Clone a failed/rejected execution as a new pending execution."""
        res = await db.execute(
            select(RunExecution).where(
                RunExecution.id == exec_id,
                RunExecution.run_id == run_id,
            )
        )
        original = res.scalars().first()
        if not original:
            raise ValueError(f"RunExecution {exec_id} not found")
        if original.status not in ("failed", "rejected"):
            raise ValueError(f"Only failed/rejected executions can be retried, got: {original.status}")

        new_exec = RunExecution(
            id=str(uuid.uuid4()),
            run_id=run_id,
            kind=original.kind,
            status="pending",
            risk_level=original.risk_level,
            payload=original.payload or {},
            target_device_id=original.target_device_id,
        )
        db.add(new_exec)

        # Reset run to running if it's in a terminal state
        run_res = await db.execute(
            select(AgentRun).where(AgentRun.id == run_id)
        )
        run = run_res.scalars().first()
        if run and run.status in ("completed", "failed", "canceled"):
            run.status = "running"
            run.finished_at = None

        await db.commit()
        await db.refresh(new_exec)
        logger.info("execution.retried original=%s new=%s run=%s", exec_id, new_exec.id, run_id)
        return new_exec

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

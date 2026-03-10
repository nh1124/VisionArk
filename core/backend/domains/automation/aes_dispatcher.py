import asyncio
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from infrastructure.queue.manager import QueueManager
from domains.automation.schedule import next_run_at_utc
from shared.database import ScheduledTask, ScheduledTaskStatus, TaskType


class AESDispatcher:
    """
    Automated Execution System (AES) Dispatcher.
    Dispatches scheduled_tasks to the worker queue.
    """

    def __init__(self, session_maker):
        self.session_maker = session_maker
        self.queue_manager = QueueManager()

    async def run_forever(self, interval_seconds: int = 10):
        """Main loop for the dispatcher"""
        print(f"[AES Dispatcher] Starting loop (Interval: {interval_seconds}s)...")
        while True:
            try:
                await self.dispatch_pending_tasks()
            except Exception as e:
                print(f"[AES Dispatcher] Error in loop: {e}")

            await asyncio.sleep(interval_seconds)

    async def dispatch_pending_tasks(self):
        """Find due tasks and send them to the worker queue."""
        now = datetime.utcnow()

        async with self.session_maker() as session:
            dispatched = await self._dispatch_due_scheduled_tasks(session, now)
            if dispatched > 0:
                await session.commit()

    async def _dispatch_due_scheduled_tasks(self, session, now: datetime) -> int:
        stmt = select(ScheduledTask).filter(
            ScheduledTask.status == ScheduledTaskStatus.PENDING,
            ScheduledTask.scheduled_at <= now,
        )
        result = await session.execute(stmt)
        tasks = result.scalars().all()
        if not tasks:
            return 0

        print(f"[AES Dispatcher] Found {len(tasks)} due ScheduledTask records.")

        for task in tasks:
            task.status = ScheduledTaskStatus.PROCESSING
            task.last_run_at = now

            context = {
                "scheduled_task_id": task.id,
                "project_id": task.project_id,
                "trace_id": task.trace_id,
                "origin_type": task.origin_type,
                "origin_id": task.origin_id,
                **(task.payload or {}),
            }

            await self.queue_manager.enqueue(
                user_id=task.user_id,
                message=f"AES System Task: {task.task_type}",
                context=context,
                task_type=TaskType.AES_SYSTEM_TASK,
            )

        return len(tasks)

    async def schedule_task(
        self,
        user_id: str,
        task_type: str,
        scheduled_at: datetime,
        project_id: str = None,
        payload: dict = None,
        recurring_rule: str = None,
        trace_id: str | None = None,
        origin_type: str | None = None,
        origin_id: str | None = None,
        db_session: AsyncSession | None = None,
    ):
        """API/Service method to programmatically schedule a task.

        Delegates to AESSchedulerService for consistent task creation.
        """
        from domains.automation.aes_scheduler_service import AESSchedulerService

        if db_session is not None:
            svc = AESSchedulerService(db_session)
            return await svc.create_task(
                user_id=user_id,
                task_type=task_type,
                scheduled_at=scheduled_at,
                project_id=project_id,
                payload=payload,
                recurring_rule=recurring_rule,
                trace_id=trace_id,
                origin_type=origin_type,
                origin_id=origin_id,
            )

        async with self.session_maker() as session:
            svc = AESSchedulerService(session)
            return await svc.create_task(
                user_id=user_id,
                task_type=task_type,
                scheduled_at=scheduled_at,
                project_id=project_id,
                payload=payload,
                recurring_rule=recurring_rule,
                trace_id=trace_id,
                origin_type=origin_type,
                origin_id=origin_id,
            )

    @staticmethod
    def calculate_next_run(rule: str, last_run: datetime, timezone_name: str = "UTC") -> datetime:
        """Calculate next-run timestamp from recurring_rule in UTC."""
        if not rule:
            return None

        try:
            return next_run_at_utc(rule, timezone_name, after_utc=last_run)
        except Exception:
            if rule == "@daily":
                return last_run + timedelta(days=1)
            if rule == "@weekly":
                return last_run + timedelta(weeks=1)
            if rule == "@hourly":
                return last_run + timedelta(hours=1)
            return last_run + timedelta(days=1)

    async def reschedule_task(self, original_task: ScheduledTask, next_run: datetime):
        """Creates a new task based on an existing recurring task.

        Delegates to AESSchedulerService for consistent task creation.
        """
        from domains.automation.aes_scheduler_service import AESSchedulerService

        async with self.session_maker() as session:
            svc = AESSchedulerService(session)
            return await svc.reschedule_from(original_task, next_run)


import asyncio
from datetime import datetime, timedelta
from sqlalchemy import select

from shared.database import ScheduledTask, ScheduledTaskStatus
from infrastructure.queue.manager import QueueManager

class AESDispatcher:
    """
    Automated Execution System (AES) Dispatcher.
    Monitors the ScheduledTask table and dispatches tasks to the Redis queue.
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
        """Finds due tasks and sends them to the worker queue"""
        now = datetime.utcnow()
        
        async with self.session_maker() as session:
            # 1. Fetch pending tasks that are due
            stmt = select(ScheduledTask).filter(
                ScheduledTask.status == ScheduledTaskStatus.PENDING,
                ScheduledTask.scheduled_at <= now
            )
            result = await session.execute(stmt)
            tasks = result.scalars().all()
            
            if not tasks:
                return

            print(f"[AES Dispatcher] Found {len(tasks)} due tasks. Dispatching...")
            
            for task in tasks:
                # 2. Update status to prevent double-dispatch in a distributed environment
                task.status = ScheduledTaskStatus.PROCESSING
                task.last_run_at = now
                
                # 3. Enqueue to Redis
                context = {
                    "scheduled_task_id": task.id,
                    "project_id": task.project_id,
                    **task.payload
                }
                
                from shared.database import TaskType
                await self.queue_manager.enqueue(
                    user_id=task.user_id,
                    message=f"AES System Task: {task.task_type}",
                    context=context,
                    task_type=TaskType.AES_SYSTEM_TASK
                )
            
            await session.commit()

    async def schedule_task(self, user_id: str, task_type: str, scheduled_at: datetime, project_id: str = None, payload: dict = None, recurring_rule: str = None):
        """API/Service method to programmatically schedule a task.
        
        Delegates to AESSchedulerService for consistent task creation.
        """
        from domains.automation.aes_scheduler_service import AESSchedulerService

        async with self.session_maker() as session:
            svc = AESSchedulerService(session)
            return await svc.create_task(
                user_id=user_id,
                task_type=task_type,
                scheduled_at=scheduled_at,
                project_id=project_id,
                payload=payload,
                recurring_rule=recurring_rule,
            )

    @staticmethod
    def calculate_next_run(rule: str, last_run: datetime) -> datetime:
        """
        Heuristic for calculating next run time. 
        In production, this would use 'croniter' for full cron support.
        """
        if not rule:
            return None
            
        if rule == "@daily":
            return last_run + timedelta(days=1)
        if rule == "@weekly":
            return last_run + timedelta(weeks=1)
        if rule == "@hourly":
            return last_run + timedelta(hours=1)
            
        # Fallback for unknown rules: daily
        return last_run + timedelta(days=1)

    async def reschedule_task(self, original_task: ScheduledTask, next_run: datetime):
        """Creates a new task based on an existing recurring task.
        
        Delegates to AESSchedulerService for consistent task creation.
        """
        from domains.automation.aes_scheduler_service import AESSchedulerService

        async with self.session_maker() as session:
            svc = AESSchedulerService(session)
            return await svc.reschedule_from(original_task, next_run)


import asyncio
import json
import uuid
from datetime import datetime, timedelta
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from models.database import ScheduledTask, ScheduledTaskStatus
from queue_system.manager import QueueManager

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
                # (Though here we likely have only one dispatcher)
                task.status = ScheduledTaskStatus.PROCESSING
                task.last_run_at = now
                
                # 3. Enqueue to Redis
                # We use a specific task_type for the worker to recognize
                context = {
                    "scheduled_task_id": task.id,
                    "project_id": task.project_id,
                    **task.payload
                }
                
                self.queue_manager.enqueue(
                    user_id=task.user_id,
                    message=f"AES System Task: {task.task_type}",
                    context=context,
                    task_type="aes_system_task"
                )
            
            await session.commit()

    async def schedule_task(self, user_id: str, task_type: str, scheduled_at: datetime, project_id: str = None, payload: dict = None, recurring_rule: str = None):
        """API/Service method to programmatically schedule a task"""
        async with self.session_maker() as session:
            new_task = ScheduledTask(
                id=str(uuid.uuid4()),
                user_id=user_id,
                project_id=project_id,
                task_type=task_type,
                payload=payload or {},
                scheduled_at=scheduled_at,
                recurring_rule=recurring_rule,
                status=ScheduledTaskStatus.PENDING
            )
            session.add(new_task)
            await session.commit()
            print(f"[AES Dispatcher] Scheduled task {task_type} for {scheduled_at}")
            return new_task.id

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
        """
        Creates a new task based on an existing recurring task.
        """
        async with self.session_maker() as session:
            new_task = ScheduledTask(
                id=str(uuid.uuid4()),
                user_id=original_task.user_id,
                project_id=original_task.project_id,
                task_type=original_task.task_type,
                payload=original_task.payload,
                scheduled_at=next_run,
                recurring_rule=original_task.recurring_rule,
                status=ScheduledTaskStatus.PENDING
            )
            session.add(new_task)
            await session.commit()
            print(f"[AES Dispatcher] Rescheduled recurring task {original_task.task_type} for {next_run}")
            return new_task.id

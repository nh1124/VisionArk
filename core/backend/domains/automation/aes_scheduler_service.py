"""
AES Scheduler Service - Single source of truth for creating/updating ScheduledTasks.

Consolidates scheduling logic previously duplicated between:
  - api/automation.py (POST /schedule, PUT /tasks/{task_id})
  - AESDispatcher.schedule_task() / reschedule_task()
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.database import ScheduledTask, ScheduledTaskStatus


class AESSchedulerService:
    """Centralised service for ScheduledTask lifecycle."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ #
    #  Create
    # ------------------------------------------------------------------ #
    async def create_task(
        self,
        user_id: str,
        task_type: str,
        scheduled_at: datetime,
        project_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        recurring_rule: Optional[str] = None,
        trace_id: Optional[str] = None,
        origin_type: Optional[str] = None,
        origin_id: Optional[str] = None,
    ) -> str:
        """Create a new ScheduledTask with normalised timestamp.

        Returns the new task id.
        """
        scheduled_at = self._normalise_dt(scheduled_at)

        new_task = ScheduledTask(
            id=str(uuid.uuid4()),
            user_id=user_id,
            project_id=project_id,
            task_type=task_type,
            payload=payload or {},
            scheduled_at=scheduled_at,
            recurring_rule=recurring_rule,
            trace_id=trace_id,
            origin_type=origin_type,
            origin_id=origin_id,
            status=ScheduledTaskStatus.PENDING,
        )
        self.db.add(new_task)
        await self.db.commit()
        print(f"[AESSchedulerService] Created task {task_type} ({new_task.id}) for {scheduled_at}")
        return new_task.id

    # ------------------------------------------------------------------ #
    #  Update
    # ------------------------------------------------------------------ #
    async def update_task(
        self,
        task: ScheduledTask,
        task_type: str,
        scheduled_at: datetime,
        project_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        recurring_rule: Optional[str] = None,
        trace_id: Optional[str] = None,
        origin_type: Optional[str] = None,
        origin_id: Optional[str] = None,
    ) -> None:
        """Update an existing ScheduledTask and reset to PENDING."""
        task.project_id = project_id
        task.task_type = task_type
        task.payload = payload or {}
        task.scheduled_at = self._normalise_dt(scheduled_at)
        task.recurring_rule = recurring_rule
        task.trace_id = trace_id
        task.origin_type = origin_type
        task.origin_id = origin_id
        task.status = ScheduledTaskStatus.PENDING
        await self.db.commit()

    # ------------------------------------------------------------------ #
    #  Reschedule (recurring tasks)
    # ------------------------------------------------------------------ #
    async def reschedule_from(
        self,
        original: ScheduledTask,
        next_run: datetime,
    ) -> str:
        """Clone a recurring task for its next execution.

        Returns the new task id.
        """
        return await self.create_task(
            user_id=original.user_id,
            task_type=original.task_type,
            scheduled_at=next_run,
            project_id=original.project_id,
            payload=original.payload,
            recurring_rule=original.recurring_rule,
            trace_id=original.trace_id,
            origin_type=original.origin_type,
            origin_id=original.origin_id,
        )

    # ------------------------------------------------------------------ #
    #  Helpers
    # ------------------------------------------------------------------ #
    @staticmethod
    def _normalise_dt(dt: datetime) -> datetime:
        """Convert tz-aware datetime to naive UTC for DB storage."""
        if dt.tzinfo is not None:
            if dt.tzinfo != timezone.utc:
                dt = dt.astimezone(timezone.utc)
            dt = dt.replace(tzinfo=None)
        return dt

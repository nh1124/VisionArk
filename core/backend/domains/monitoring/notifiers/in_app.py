from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from domains.monitoring.models import NotificationResult
from domains.monitoring.notifiers.base import BaseNotifier
from domains.workspace.notification_service import NotificationService
from shared.database import NotificationType


class InAppNotifier(BaseNotifier):
    def __init__(self, db: AsyncSession):
        self.db = db

    async def notify(self, *, user_id: str, title: str, content: str, link: str | None = None) -> NotificationResult:
        service = NotificationService(self.db)
        await service.create_notification(
            user_id=user_id,
            title=title,
            content=content,
            type=NotificationType.WARNING,
            link=link,
        )
        return NotificationResult(
            sent=True,
            channel="in_app",
            detail="notification_created",
            sent_at=datetime.utcnow(),
        )

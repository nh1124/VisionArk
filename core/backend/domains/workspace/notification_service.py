import json
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from shared.database import Notification, NotificationType
from infrastructure.queue.manager import QueueManager

class NotificationService:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.queue_manager = QueueManager()

    async def create_notification(
        self,
        user_id: str,
        title: str,
        content: str,
        type: NotificationType = NotificationType.INFO,
        project_id: Optional[str] = None,
        link: Optional[str] = None
    ) -> Notification:
        """Create a notification, save to DB, and broadcast via Redis."""
        notification = Notification(
            id=str(uuid.uuid4()),
            user_id=user_id,
            project_id=project_id,
            type=type.value if isinstance(type, NotificationType) else type,
            title=title,
            content=content,
            link=link,
            is_read=False,
            created_at=datetime.utcnow()
        )
        
        self.db.add(notification)
        await self.db.commit()
        await self.db.refresh(notification)

        # Broadcast via Redis Pub/Sub
        await self._broadcast(notification)
        
        return notification

    async def _broadcast(self, notification: Notification):
        """Publish notification event to Redis Pub/Sub for real-time delivery."""
        payload = {
            "type": "notification",
            "data": {
                "id": notification.id,
                "user_id": notification.user_id,
                "project_id": notification.project_id,
                "type": notification.type,
                "title": notification.title,
                "content": notification.content,
                "link": notification.link,
                "is_read": notification.is_read,
                "created_at": notification.created_at.isoformat()
            }
        }
        
        # Use Redis client from QueueManager to publish
        channel = f"notifications:{notification.user_id}"
        await self.queue_manager.client.publish(channel, json.dumps(payload))
        print(f"[NotificationService] Broadcasted to {channel}: {notification.title}")

    async def get_unread_count(self, user_id: str) -> int:
        """Get count of unread notifications for a user."""
        from sqlalchemy import func
        stmt = select(func.count(Notification.id)).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def list_notifications(self, user_id: str, limit: int = 50, offset: int = 0) -> List[Notification]:
        """List notifications for a user, sorted by most recent."""
        stmt = select(Notification).filter(
            Notification.user_id == user_id
        ).order_by(desc(Notification.created_at)).limit(limit).offset(offset)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def mark_as_read(self, notification_id: str, user_id: str):
        """Mark a specific notification as read."""
        stmt = select(Notification).filter(
            Notification.id == notification_id,
            Notification.user_id == user_id
        )
        result = await self.db.execute(stmt)
        notification = result.scalar_one_or_none()
        
        if notification:
            notification.is_read = True
            await self.db.commit()
            return True
        return False

    async def mark_all_as_read(self, user_id: str):
        """Mark all notification as read for a user."""
        from sqlalchemy import update
        stmt = update(Notification).filter(
            Notification.user_id == user_id,
            Notification.is_read == False
        ).values(is_read=True)
        
        await self.db.execute(stmt)
        await self.db.commit()
        return True

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession

from domains.monitoring.models import NotificationResult


class BaseNotifier(ABC):
    @abstractmethod
    async def notify(self, *, user_id: str, title: str, content: str, link: str | None = None) -> NotificationResult:
        raise NotImplementedError


def get_notifier(channel: str, db: AsyncSession) -> BaseNotifier:
    normalized = (channel or "in_app").lower()
    if normalized in {"in_app", "app", "notification"}:
        from domains.monitoring.notifiers.in_app import InAppNotifier

        return InAppNotifier(db)
    raise ValueError(f"Unsupported notify channel: {channel}")

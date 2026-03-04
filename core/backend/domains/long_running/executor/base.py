"""Base class and registration decorator for Long-Running Job handlers."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from shared.database import LongRunningJob
    from domains.long_running.services.job_service import LongRunningJobService

logger = logging.getLogger(__name__)


class BaseLRJHandler(ABC):
    """Abstract base for all long-running job handlers."""

    job_kind: ClassVar[str] = ""

    @abstractmethod
    async def run(
        self,
        job: "LongRunningJob",
        svc: "type[LongRunningJobService]",
        db: "AsyncSession",
    ) -> None: ...


def register_lrj_handler(job_kind: str):
    """Class decorator that registers a BaseLRJHandler subclass in lrj_registry.

    Usage::

        @register_lrj_handler("research.gemini.deep")
        class DeepResearchJobHandler(BaseLRJHandler):
            async def run(self, job, svc, db): ...
    """
    def decorator(cls: type) -> type:
        if not (isinstance(cls, type) and issubclass(cls, BaseLRJHandler)):
            raise TypeError(f"{cls.__name__} must subclass BaseLRJHandler")
        from va_sdk.registry import lrj_registry
        lrj_registry.register(job_kind)(cls)
        logger.debug("[LRJRegistry] Registered handler %s for kind: %s", cls.__name__, job_kind)
        return cls
    return decorator

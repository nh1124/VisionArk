from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from shared.database import MonitorJob
from domains.monitoring.models import CollectionResult


class BaseCollector(ABC):
    @abstractmethod
    async def collect(self, job: MonitorJob) -> CollectionResult:
        raise NotImplementedError


def get_collector(source_type: str) -> BaseCollector:
    normalized = (source_type or "").upper()
    if normalized in {"URL", "HTTP", "WEB"}:
        from domains.monitoring.collectors.url_collector import URLCollector

        return URLCollector()
    raise ValueError(f"Unsupported source_type: {source_type}")

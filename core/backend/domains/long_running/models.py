"""Domain models for the long_running job infrastructure."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class JobStatus(str, Enum):
    QUEUED    = "queued"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    EXPIRED   = "expired"
    CANCELLED = "cancelled"


class JobEventType(str, Enum):
    CREATED   = "created"
    QUEUED    = "queued"
    RUNNING   = "running"
    PROGRESS  = "progress"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"
    EXPIRED   = "expired"


@dataclass
class JobCreateOptions:
    """Options passed when creating a new LongRunningJob."""
    sync_timeout_sec: int = 300
    max_retries: int = 0
    external_ref: Optional[str] = None
    result_path: Optional[str] = None
    project_id: Optional[str] = None
    session_id: Optional[str] = None

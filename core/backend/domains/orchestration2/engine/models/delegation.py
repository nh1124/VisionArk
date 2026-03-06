"""Delegation models."""

from __future__ import annotations

from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field

from .message import Message


class DelegationResultStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class DelegationDeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"


class DelegationRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    parent_run_id: str
    child_agent_name: str
    task: str
    timeout_sec: int | None = None
    request_id: str | None = None
    context_scope: str | None = None


class DelegationResult(BaseModel):
    delegation_id: str
    child_run_id: str
    status: DelegationResultStatus
    output_message: Message | None = None
    error: str | None = None
    delivery_status: DelegationDeliveryStatus | None = None
    delivery_cursor: int | None = None

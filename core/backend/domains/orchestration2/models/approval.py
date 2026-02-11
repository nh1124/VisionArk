"""Approval-related models."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field

from .common import ApprovalSourceType


class ApprovalRequest(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    source_type: ApprovalSourceType
    source_name: str
    reason: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class ApprovalDecision(BaseModel):
    request_id: str
    approved: bool
    comment: str | None = None


class PendingAction(BaseModel):
    approval_request_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    step_id: str
    action_type: ApprovalSourceType
    action_name: str
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

"""Run context and record models."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .common import RunStatus
from .message import Message


class RunContext(BaseModel):
    active_skill: str | None = None
    active_step_id: str | None = None
    turn_index: int = 0
    tool_call_count: int = 0


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: RunStatus = RunStatus.QUEUED
    agent_name: str
    graph_name: str
    input_message: Message | None = None
    history: list[Message] = Field(default_factory=list)
    output_message: Message | None = None
    current_step_id: str | None = None
    pending_approval_ids: list[str] = Field(default_factory=list)
    pending_delegation_ids: list[str] = Field(default_factory=list)
    context: RunContext = Field(default_factory=RunContext)
    metadata: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow
    )

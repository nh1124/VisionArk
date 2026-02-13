"""Message and SubMessage models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .common import MessageRole, SubMessageKind


class ToolCallRef(BaseModel):
    tool_name: str
    call_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    provider_data: dict[str, Any] = Field(default_factory=dict)


class SubMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    kind: SubMessageKind
    content: str
    tool_call: ToolCallRef | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    role: MessageRole
    content: str
    submessages: list[SubMessage] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

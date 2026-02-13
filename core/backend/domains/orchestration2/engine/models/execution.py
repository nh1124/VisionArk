"""Execution context and result models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, Field

from .approval import ApprovalRequest
from .common import EventSource, EventType
from .delegation import DelegationRequest
from .message import Message

if TYPE_CHECKING:
    from ..interfaces.store import Store
    from .agent import AgentDef
    from .run import RunContext


class ExecutionContext(BaseModel):
    """Context passed to tools, skills, and roles during execution.

    The ``metadata`` dict is a generic extension point for host applications.
    orchestration2 core never reads from it — tools, skills, and roles owned
    by the host app can store whatever they need (e.g. project_id, user_id,
    db_session, api_key).
    """

    model_config = {"arbitrary_types_allowed": True}

    run_id: str
    agent_def: Any  # AgentDef (avoid circular import at runtime)
    run_context: Any  # RunContext
    store: Any  # Store reference
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    call_id: str
    output: str
    error: str | None = None


class SkillResult(BaseModel):
    skill_name: str
    output: str
    messages: list[Message] = Field(default_factory=list)
    error: str | None = None


class RoleResult(BaseModel):
    role_name: str
    output: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    done: bool = False


class OrchestrationEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    type: EventType
    run_id: str
    step_id: str
    source: EventSource
    detail: str | None = None
    created_at: datetime = Field(
        default_factory=datetime.utcnow
    )


class RunResponse(BaseModel):
    run_id: str
    completed: bool
    message: Message | None = None
    history: list[Message] = Field(default_factory=list)
    approval_requests: list[ApprovalRequest] = Field(default_factory=list)
    delegation_requests: list[DelegationRequest] = Field(default_factory=list)


class LLMResponse(BaseModel):
    content: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    finish_reason: str | None = None

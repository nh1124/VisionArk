"""Common enums and value types for orchestration2."""

from enum import Enum


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class SubMessageKind(str, Enum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    REASONING = "reasoning"


class ApprovalSourceType(str, Enum):
    TOOL = "tool"
    SKILL = "skill"


class RunStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_DELEGATION = "waiting_delegation"
    COMPLETED = "completed"
    FAILED = "failed"


class ApprovalPolicy(str, Enum):
    AUTO = "auto"
    REQUIRED = "required"
    NEVER = "never"


class EventType(str, Enum):
    SKILL_SELECTED = "skill_selected"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    NEEDS_APPROVAL = "needs_approval"
    APPROVED = "approved"
    DENIED = "denied"
    DELEGATE_TASK = "delegate_task"
    DELEGATION_DONE = "delegation_done"
    DELEGATION_FAILED = "delegation_failed"
    DONE = "done"
    ERROR = "error"


class EventSource(str, Enum):
    ROLE = "role"
    SKILL = "skill"
    APPROVAL = "approval"
    DELEGATION = "delegation"
    SYSTEM = "system"

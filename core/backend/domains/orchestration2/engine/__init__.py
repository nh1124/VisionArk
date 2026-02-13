"""orchestration2 engine — pure, reusable agent execution core.

Public API:
    AgentEngine          — main facade
    Errors               — via .errors module
    Models               — via .models subpackage
    Interfaces           — via .interfaces subpackage
    Registry             — via .registry subpackage
    Orchestration        — via .orchestration subpackage
    Store                — via .store subpackage
"""

from .agent_engine import AgentEngine
from .errors import (
    AgentNotFoundError,
    DelegationError,
    DuplicateNameError,
    GraphValidationError,
    LimitsExceededError,
    OrchestrationError,
    RegistryKeyError,
    RunNotFoundError,
    SkillExecutionError,
    ToolExecutionError,
    ToolNotAllowedError,
)

__all__ = [
    "AgentEngine",
    "AgentNotFoundError",
    "DelegationError",
    "DuplicateNameError",
    "GraphValidationError",
    "LimitsExceededError",
    "OrchestrationError",
    "RegistryKeyError",
    "RunNotFoundError",
    "SkillExecutionError",
    "ToolExecutionError",
    "ToolNotAllowedError",
]

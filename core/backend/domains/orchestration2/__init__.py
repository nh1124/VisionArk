"""orchestration2 — Type-safe, registry-driven agent execution engine.

Public API:
    AgentEngine          — main facade
    Models               — via .models subpackage
    Interfaces           — via .interfaces subpackage
    Errors               — via .errors module
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

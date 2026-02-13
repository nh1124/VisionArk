"""Custom exceptions for orchestration2."""


class OrchestrationError(Exception):
    """Base exception for orchestration2."""


class ToolExecutionError(OrchestrationError):
    """Raised when a tool invocation fails."""


class ToolNotAllowedError(OrchestrationError):
    """Raised when a tool is not in the active skill's allowed tools list."""

    def __init__(self, tool_name: str, skill_name: str) -> None:
        self.tool_name = tool_name
        self.skill_name = skill_name
        super().__init__(
            f"Tool '{tool_name}' is not allowed by skill '{skill_name}'"
        )


class SkillExecutionError(OrchestrationError):
    """Raised when a skill execution fails."""


class GraphValidationError(OrchestrationError):
    """Raised when a graph spec fails validation."""


class RunNotFoundError(OrchestrationError):
    """Raised when a run_id cannot be found in the store."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Run '{run_id}' not found")


class DelegationError(OrchestrationError):
    """Raised when a delegation operation fails."""


class AgentNotFoundError(OrchestrationError):
    """Raised when an agent cannot be found."""


class RegistryKeyError(OrchestrationError):
    """Raised when a registry lookup fails."""

    def __init__(self, registry_name: str, key: str) -> None:
        self.registry_name = registry_name
        self.key = key
        super().__init__(f"'{key}' not found in {registry_name}")


class DuplicateNameError(OrchestrationError):
    """Raised when a registry entry with the same name already exists."""

    def __init__(self, registry_name: str, name: str) -> None:
        self.registry_name = registry_name
        self.name = name
        super().__init__(f"'{name}' already exists in {registry_name}")


class LimitsExceededError(OrchestrationError):
    """Raised when agent run limits (turns, tool calls, etc.) are exceeded."""

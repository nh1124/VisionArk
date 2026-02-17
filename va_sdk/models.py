"""Core SDK types for VisionArk integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from abc import ABC, abstractmethod

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class IntegrationContext:
    """Context object passed to integration tools at runtime."""
    user_id: str
    db: AsyncSession
    project_id: Optional[str] = None
    session_id: Optional[str] = None
    api_key: Optional[str] = None
    user_settings: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


@dataclass
class ToolResult:
    """Standard return type from an integration tool invocation."""
    content: str
    data: Optional[Any] = None
    is_success: bool = True
    attachments: list = field(default_factory=list)


@dataclass
class ToolAttachment:
    """A file or data attachment returned alongside a ToolResult."""
    filename: str
    mime_type: str
    data: Optional[bytes] = None
    url: Optional[str] = None


class BaseTool(ABC):
    """Abstract base class for integration tools.

    Subclasses must define:
        name: str           - unique tool identifier
        description: str    - human-readable description
        args_schema          - optional pydantic model for arguments

    And implement the ``run`` method.
    """
    name: str = ""
    description: str = ""
    args_schema: Any = None

    @abstractmethod
    async def run(self, *args, **kwargs) -> Any:
        ...

"""LLM provider interface protocol."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from ..models.execution import LLMResponse
from ..models.message import Message


@runtime_checkable
class LLMProvider(Protocol):
    async def complete(
        self,
        messages: list[Message],
        *,
        system: str | None = None,
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
    ) -> LLMResponse: ...

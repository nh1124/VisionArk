"""Tool interface protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..models.execution import ExecutionContext, ToolResult
    from ..models.message import ToolCallRef
    from ..models.tool import ToolDef


@runtime_checkable
class BaseTool(Protocol):
    definition: ToolDef

    async def invoke(
        self, call: ToolCallRef, ctx: ExecutionContext
    ) -> ToolResult: ...

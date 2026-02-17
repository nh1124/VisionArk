"""Tool dispatcher — resolves and invokes tools during engine runs.

Resolution order:
1. If an engine-specific ``EngineToolAdapter`` is registered for the tool
   name *and* the current engine kind, use it.
2. Otherwise fall back to the common ``BaseTool.invoke()`` path.

Adapter lookup is keyed on **tool name only** (design §5.5).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from ..models.execution import ExecutionContext, ToolResult
from ..models.message import ToolCallRef

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .tool_registry import ToolRegistry

logger = logging.getLogger(__name__)


# ── Adapter protocol (engine-specific overrides) ─────────────────────


@runtime_checkable
class EngineToolAdapter(Protocol):
    """Optional specialisation for a tool on a specific engine."""

    def can_handle(self, engine_kind: str, tool_name: str) -> bool: ...

    async def invoke_native(
        self,
        engine_kind: str,
        call: ToolCallRef,
        ctx: ExecutionContext,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ToolResult: ...


# ── Dispatcher ───────────────────────────────────────────────────────


class ToolDispatcher:
    """Resolves the right tool implementation and invokes it."""

    def __init__(
        self,
        tool_registry: ToolRegistry,
        adapters: list[EngineToolAdapter] | None = None,
    ) -> None:
        self._registry = tool_registry
        self._adapters: list[EngineToolAdapter] = list(adapters or [])

    def register_adapter(self, adapter: EngineToolAdapter) -> None:
        self._adapters.append(adapter)

    async def dispatch(
        self,
        engine_kind: str,
        call: ToolCallRef,
        ctx: ExecutionContext,
        *,
        extra: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Dispatch a tool invocation, preferring engine-specific adapters."""
        # 1. Check adapters
        for adapter in self._adapters:
            if adapter.can_handle(engine_kind, call.tool_name):
                logger.debug(
                    "tool_dispatch: using adapter for '%s' (engine=%s)",
                    call.tool_name,
                    engine_kind,
                )
                return await adapter.invoke_native(
                    engine_kind, call, ctx, extra=extra
                )

        # 2. Fallback to common tool registry
        from ..errors import RegistryKeyError

        try:
            _tool_def, tool_impl = self._registry.get(call.tool_name)
        except RegistryKeyError:
            return ToolResult(
                tool_name=call.tool_name,
                call_id=call.call_id,
                output=f"Error: Tool '{call.tool_name}' not found",
                error=f"Tool '{call.tool_name}' not found",
            )

        logger.debug(
            "tool_dispatch: common path for '%s'", call.tool_name
        )
        return await tool_impl.invoke(call, ctx)
